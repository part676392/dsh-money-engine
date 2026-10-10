#!/usr/bin/env python3
"""選考データベース サイト生成器.

診断で確定した病巣:
  - 有料note 350本の可視テキストはクロール可能なのに engagement 0.38/本
  - 無料は 1.90/本 (5.0倍) → 無料の入口が存在しないのが転換阻害
  - ES対象24社中 funnel完成は2社、15社が有料のみ=検索から見えない

治療: 既存在庫(企業×選考)を横断検索できる無料の入口を自社ドメインに作り、
      各社ページから君のnote(無料フック/有料深掘り)へ送客する。
      毎晩cronで再実行し、締切の変化を history として積む = 後から取れない堀。
"""
from __future__ import annotations

import collections
import html
import urllib.parse
import json
import pathlib
import re
import datetime as dt

import demand

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT
DATA = ROOT / "data"


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


OPERATOR = {
    "name": "転職ナビ・中途キャリアの研究所",
    "credential": "元人事の採用担当。書類選考から最終面接まで、数多くの候補者を評価してきた「選ぶ側」の視点。",
    "note": "https://note.com/shushoku_career1",
}

def tracker(key: str) -> str:
    """访问計. f-string の中で JS の {} を書くと置換フィールドに化けるので,
    文字列はここで組み立てて field 1 個として埋める."""
    return (
        '<script>(function(){try{fetch("'
        + "https://abacus.jasoncameron.dev/hit/dsh-money-engine/"
        + key
        + '", {mode:"no-cors",keepalive:true});}catch(e){}})();</script>'
    )


TRACKER_HOME = tracker("home")
TRACKER_COMPANY = tracker("company")


def load() -> dict:
    corpus = json.load(open(ROOT / "data" / "corpus_full.json", encoding="utf-8"))
    es = json.load(open(ROOT / "data" / "es_dataset.json", encoding="utf-8"))
    return {"corpus": corpus, "es": es}


def price_badge(p: int) -> str:
    return "🆓 無料" if not p else f"¥{p:,}"


def classify(t: str) -> str:
    if re.search(r"障害者採用|障がい者採用", t):
        return "障害者採用"
    if re.search(r"ES|ガクチカ", t):
        return "新卒ES"
    if re.search(r"最終面接|役員面接", t):
        return "最終面接"
    if re.search(r"中途面接対策", t):
        return "中途面接"
    if re.search(r"面接想定PDF", t):
        return "面接想定100選"
    return "その他"


def company_of(t: str) -> str:
    for pat in (
        r"【中途・転職】グッと内定が近づく！(.+?)\s*(?:〈|最終面接|想定)",
        r"^(.+?)の中途面接対策",
        r"^(.+?)\s*(?:障害者|障がい者)採用",
        r"^(.+?)のES",
        r"^(.+?)\s+(?:中途|面接)",
    ):
        m = re.search(pat, t)
        if m:
            c = re.sub(r"【[^】]*】", "", m.group(1)).strip(" ・、")
            if 1 < len(c) <= 30:
                return c
    return ""


def price_label(p: int) -> str:
    return "無料" if not p else f"¥{p:,}"


def build(d: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "data").mkdir(exist_ok=True)
    corpus, es = d["corpus"], d["es"]

    recs = []
    for n in corpus:
        t = n.get("name") or ""
        recs.append(
            {
                "company": company_of(t),
                "kind": classify(t),
                "title": t,
                "price": n.get("price") or 0,
                "likes": n.get("likeCount") or 0,
                "url": f"https://note.com/shushoku_career1/n/{n.get('key')}",
                "published": (n.get("publishAt") or "")[:10],
            }
        )

    by_company = collections.defaultdict(list)
    for r in recs:
        if r["company"]:
            by_company[r["company"]].append(r)

    dem = demand.load()

    kind_stat = collections.Counter(r["kind"] for r in recs)
    priced = sum(r["price"] for r in recs)
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))

    # ---- 機械可読データ（cron が毎晩追記 → 変化の履歴が堀になる） ----
    snapshot = {
        "captured_at": now.isoformat(timespec="seconds"),
        "source": "https://note.com/shushoku_career1 (public API v2)",
        "articles": len(recs),
        "companies": len(by_company),
        "listed_value_yen": priced,
        "by_kind": dict(kind_stat),
        "records": recs,
    }
    (OUT / "data" / "snapshot-latest.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    hist = DATA / "history"
    hist.mkdir(exist_ok=True)
    (hist / f"{now:%Y-%m-%d}.json").write_text(
        json.dumps({k: snapshot[k] for k in ("captured_at", "articles", "companies", "listed_value_yen", "by_kind")}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    if dem:
        demand.dump_for_site(dem, by_company, OUT)

    # ---- index.html : answer unit として独立して意味を持たせる ----
    rows = []
    for comp in sorted(by_company, key=lambda c: -len(by_company[c])):
        g = by_company[comp]
        free = [x for x in g if x["price"] == 0]
        paid = [x for x in g if x["price"] > 0]
        links = " / ".join(
            f'<a href="{esc(x["url"])}">{esc(x["published"])} {price_label(x["price"])}</a>' for x in g[:3]
        )
        rows.append(
            f"<tr><td><a href='company/{esc(comp)}.html'>{esc(comp)}</a></td>"
            f"<td>{len(g)}</td><td>{len(free)}</td><td>{len(paid)}</td>"
            f"<td>{esc('、'.join(sorted({x['kind'] for x in g})))}</td><td>{links}</td></tr>"
        )


    demand_html = demand.themes_block(dem, by_company) if dem else ""

    free_recs = [r for r in recs if r["price"] == 0]
    free_recs.sort(key=lambda r: (-r["likes"], r["published"]), reverse=False)
    free_recs.sort(key=lambda r: -r["likes"])
    fl = []
    for r in free_recs:
        fl.append(
            "<li><a href='%s'>%s</a><span class='lk'>%dスキ</span>"
            "<span class='d'>%s</span></li>" % (r["url"], esc(r["title"]), r["likes"], esc(r["published"]))
        )
    free_block = (
        "<div class='free'><h2>🆓 無料で読める %d 本"
        " <small>（全 %d 本の %.1f%% / スキ数は平均 %.1f 倍）</small></h2><ul>%s</ul></div>"
        % (
            len(free_recs),
            len(recs),
            len(free_recs) / max(len(recs), 1) * 100,
            (sum(r["likes"] for r in free_recs) / max(len(free_recs), 1))
            / max(
                sum(r["likes"] for r in recs if r["price"]) / max(sum(1 for r in recs if r["price"]), 1),
                0.01,
            ),
            "".join(fl),
        )
    )

    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Dataset",
                "name": "転職・新卒 選考対策 目録データベース",
                "description": (
                    "企業ごとに中途面接対策・新卒ES・障害者採用の対策資料が引けるか横断検索できる目録。"
                    "登録記事数、無料/有料の内訳、公開日を毎日更新。"
                ),
                "dateModified": snapshot["captured_at"],
                "creator": {"@type": "Person", "name": "転職ナビ・中途キャリアの研究所"},
                "variableMeasured": ["企業名", "選考種別", "価格", "公開日"],
                "spatialCoverage": "Japan",
            },
            {
                "@type": "ItemList",
                "name": "企業別 対策資料 一覧",
                "numberOfItems": len(by_company),
                "itemListElement": [
                    {"@type": "ListItem", "position": i + 1, "name": c, "url": f"company/{c}.html"}
                    for i, c in enumerate(sorted(by_company)[:60])
                ],
            },
        ],
    }

    kinds = "　".join(f"<b>{esc(k)}</b> {v}本" for k, v in kind_stat.most_common())
    operator_box = (
        "<section class='about'><h2>運営者について</h2>"
        + "<p class='who'><b>" + esc(OPERATOR["name"]) + "</b></p>"
        + "<p>" + esc(OPERATOR["credential"]) + "</p>"
        + "<p class='src'>この目録のデータは、note に公開済みの記事と各社の公開情報から自動生成しています。"
        + "検索需要の語は Google 自動補完で観測された実際の入力です。" + str(snapshot.get("captured_at","")) + " 時点。</p>"
        + "<p><a href='" + OPERATOR["note"] + "'>note 本体で記事を買う →</a></p></section>"
    )
    html_doc = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>転職・新卒 選考対策 目録データベース｜{len(recs)}本を企業別に横断検索</title>
<meta name="description" content="{len(recs)}本の面接対策・ES資料を企業別に検索。無料/有料の内訳と公開日を毎日自動更新。">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="https://part676392.github.io/dsh-money-engine/">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
<style>
body{{font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif;margin:0;background:#f7f8fa;color:#1b1f24;line-height:1.65}}
main{{max-width:1000px;margin:0 auto;padding:28px 18px 70px}}
h1{{font-size:1.5rem;margin:0 0 6px}}
.sub{{color:#5a6472;font-size:.9rem}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:18px 0}}
.c{{background:#fff;border:1px solid #e3e7ed;border-radius:9px;padding:13px}}
.c b{{display:block;font-size:1.5rem;line-height:1.2}}
.c span{{font-size:.76rem;color:#5a6472}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e3e7ed;border-radius:9px;overflow:hidden;font-size:.84rem}}
th{{background:#eef1f5;text-align:left;padding:9px;font-weight:600}}
td{{padding:8px 9px;border-top:1px solid #eceff3;vertical-align:top}}
tr:hover td{{background:#fbfcfd}}
a{{color:#1a5fd6;text-decoration:none}}a:hover{{text-decoration:underline}}
.about{{background:#fff;border:1px solid #e3e7ed;border-left:4px solid #1a5fd6;border-radius:9px;padding:14px 16px;margin:22px 0 10px}}
.about h2{{font-size:.98rem;margin:0 0 6px}}.about p{{font-size:.87rem;margin:7px 0}}
.who{{font-size:.95rem;margin-bottom:2px}}.src{{color:#5a6472;font-size:.8rem}}
input{{width:100%;padding:10px;border:1px solid #cfd6df;border-radius:8px;font-size:.95rem;margin:16px 0 4px;box-sizing:border-box}}
.note{{font-size:.78rem;color:#6b7480;margin-top:22px;border-top:1px solid #e3e7ed;padding-top:12px}}
a.dead{{display:block;background:#d0452c;color:#fff;padding:10px 14px;border-radius:8px;margin:14px 0 0;font-size:.9rem;text-decoration:none}}
a.dead:hover{{background:#b93a24;text-decoration:none}}
code{{background:#eef1f5;padding:1px 5px;border-radius:4px;font-size:.85em}}
.free{{background:#fff;border:1px solid #cfe3c8;border-left:4px solid #3f9d3f;border-radius:9px;padding:14px 16px;margin:18px 0}}.free h2{{font-size:1rem;margin:0 0 8px}}.free h2 small{{font-weight:400;color:#5a6472;font-size:.78rem}}.free ul{{margin:0;padding-left:18px;font-size:.85rem}}.free li{{margin:6px 0}}.demand{{background:#fff;border:1px solid #cdd9ea;border-left:4px solid #2f6fbf;border-radius:9px;padding:14px 16px;margin:18px 0}}
.demand h2{{font-size:1rem;margin:0 0 8px}}.demand h2 small{{font-weight:400;color:#5a6472;font-size:.78rem}}
.demand ul{{margin:0;padding-left:18px;font-size:.85rem;column-count:2;column-gap:22px}}
.demand li{{margin:5px 0;break-inside:avoid}}
.pc{{font-size:.73rem;background:#e6eff9;color:#1c4f8a;padding:1px 6px;border-radius:20px;margin-left:6px}}
.ax{{font-size:.72rem;color:#6b7480;margin-left:6px}}.ex{{display:block;font-size:.74rem;color:#6b7480}}
.gap{{font-size:.82rem;background:#fff8e6;border-radius:6px;padding:9px 11px;margin:10px 0 0}}
.nod{{background:#f2f7f2;border-left:4px solid #7aa87a;border-radius:6px;padding:11px 13px;font-size:.85rem;margin:16px 0}}
.lk{{font-size:.74rem;background:#e8f5e6;color:#256b25;padding:1px 6px;border-radius:20px;margin-left:6px}}.d{{font-size:.74rem;color:#6b7480;margin-left:6px}}
</style></head><body><main>
<h1>転職・新卒 選考対策 目録データベース</h1>
<a class="dead" href="es-deadlines.html">⏰ <b>28卒 コンサル ES 締切一覧</b> — 締切前の案件を日付順に。無料で読める書き方ガイド付き</a>
<p class="sub">志望企業の面接対策資料が「あるか無いか」を即答する検索窓。<b>{snapshot['captured_at']}</b> 時点・毎日自動更新</p>
<div class="cards">
<div class="c"><b>{len(recs)}</b><span>登録資料</span></div>
<div class="c"><b>{len(by_company)}</b><span>カバー企業</span></div>
<div class="c"><b>{sum(1 for r in recs if r['price']==0)}</b><span>無料で読める</span></div>
<div class="c"><b>¥{priced:,}</b><span>掲載総額</span></div>
</div>
<p class="sub">{kinds}</p>
{free_block}
{demand_html}
<input id="q" placeholder="企業名を入力（例: イオン銀行 / アビーム / NTT東日本）" oninput="f()">
<table id="t"><thead><tr><th>企業</th><th>資料数</th><th>無料</th><th>有料</th><th>選考種別</th><th>最新</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody></table>
{operator_box}
<p class="note">出典: <a href="https://note.com/shushoku_career1">note / 転職ナビ・中途キャリアの研究所</a> 公開API。機械可読データは <a href="data/snapshot-latest.json">data/snapshot-latest.json</a>、日次履歴は <code>data/history/</code> に蓄積。変化の履歴そのものが再取得不能な資産になる設計。 日々の観測の積み上がりは <a href="changes.html">運用履歴</a> に公開しています（後から再現できない実測のみ）。AI・録上面接に関する検索語の実測は <a href="ai-interviews.html">こちら</a>。 選考段階の言及集計は <a href="selection-signals.html">こちら</a>。 面接質問の実文一覧は <a href="interview-questions.html">こちら</a>。 公式選考フローの順序は <a href="selection-flows.html">こちら</a>。

</main><script>
function f(){{var v=document.getElementById('q').value.toLowerCase();
document.querySelectorAll('#t tbody tr').forEach(function(r){{
r.style.display=!v||r.textContent.toLowerCase().includes(v)?'':'none';}});}}
</script>{TRACKER_HOME}</body></html>"""
    (OUT / "index.html").write_text(html_doc, encoding="utf-8")

    # ---- 企業別ページ : AI Overview に引用される「独立した回答単位」 ----
    cdir = OUT / "company"
    cdir.mkdir(exist_ok=True)
    for comp, g in by_company.items():
        free = [x for x in g if x["price"] == 0]
        paid = [x for x in g if x["price"] > 0]
        kinds_here = sorted({x["kind"] for x in g})
        items = []
        for x in sorted(g, key=lambda y: y["published"], reverse=True):
            items.append(
                f"<li><a href='{esc(x['url'])}'>{esc(x['title'])}</a>"
                f"<span class='p'>{price_badge(x['price'])}</span>"
                f"<span class='d'>{esc(x['published'])}</span></li>"
            )
        cdem = demand.company_block(comp, dem) if dem else ""
        cai = demand.ai_block(comp, dem) if dem else ""
        ai_terms = demand.ai_demand(comp, dem) if dem else []

        q = f"{comp}の中途面接対策資料は現在{len(g)}点あります。うち{len(free)}点は無料、{len(paid)}点は有料です。"
        ltd = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": f"{comp}の面接対策資料はありますか？",
                    "acceptedAnswer": {"@type": "Answer", "text": q},
                }
            ],
        }
        if dem:
            ltd = demand.company_ld(comp, dem, ltd)
        if ai_terms:
            # AEO: 「AI面接ある?」と搜く人の問いに、観測事実と未確定事項を分けて答える
            ltd["mainEntity"].append(
                {
                    "@type": "Question",
                    "name": f"{comp}はAI面接・録上面接を実施していますか？",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": (
                            f"『{ai_terms[0]}』など AI・録上面接に関する検索が観測されています。"
                            "ただし実施するかどうかは各社の採用ページ・マイページの案内確認が必要です。"
                            "録画型では志望理由より、自己紹介・経験の要約・条件確認への即答が求められます。"
                        ),
                    },
                }
            )

        (cdir / f"{comp}.html").write_text(
            f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(comp)}の面接対策資料 {len(g)}点（無料{len(free)}/有料{len(paid)}）｜選考DB</title>
<meta name="description" content="{esc(q)}">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="https://part676392.github.io/dsh-money-engine/company/{urllib.parse.quote(comp)}.html">
<script type="application/ld+json">{json.dumps(ltd, ensure_ascii=False)}</script>
<style>body{{font-family:system-ui,"Hiragino Sans",sans-serif;margin:0;background:#f7f8fa;color:#1b1f24;line-height:1.7}}
main{{max-width:760px;margin:0 auto;padding:26px 16px 60px}}h1{{font-size:1.25rem}}
li{{margin:9px 0}}.p{{font-size:.75rem;background:#e8f0ff;color:#1a4fa0;padding:1px 7px;border-radius:20px;margin-left:6px}}
.d{{font-size:.75rem;color:#6b7480;margin-left:6px}}a{{color:#1a5fd6}}
.aigap{{background:#fff;border:1px solid #e3e7ed;border-left:4px solid #6b4fd6;border-radius:9px;padding:14px 16px;margin:20px 0}}
.aigap h2{{font-size:1rem;margin:0 0 6px}}.aigap p{{font-size:.86rem;margin:8px 0}}
.chips{{list-style:none;display:flex;flex-wrap:wrap;gap:6px;padding:0;margin:8px 0}}
.about{{background:#fff;border:1px solid #e3e7ed;border-left:4px solid #1a5fd6;border-radius:9px;padding:13px 15px;margin:20px 0}}
.about h2{{font-size:.95rem;margin:0 0 5px}}.about p{{font-size:.85rem;margin:6px 0}}
.src{{color:#5a6472;font-size:.79rem}}
.chips li{{margin:0;background:#f0edfd;color:#4b36a3;font-size:.78rem;padding:3px 9px;border-radius:20px}}</style></head><body><main>
<p><a href="../">← 目録データベースへ</a> CSV でも置いています: <a href="/dsh-money-engine/exports/interview_questions.csv">面接質問</a> ／ <a href="/dsh-money-engine/exports/selection_flows.csv">選考フロー</a> ／ <a href="/dsh-money-engine/exports/selection_signals.csv">選考段階</a> ／ <a href="/dsh-money-engine/exports/manifest.csv">列の定義</a>（UTF-8 BOM 付きで Excel でも日本語が化けない）</p>
<h1>{esc(comp)} の選考対策資料 {len(g)}点</h1>
<p>{esc(q)} 選考種別：{esc('、'.join(kinds_here))}。</p>
<ul>{chr(10).join(items)}</ul>
{cdem}
{cai}
<section class="about"><h2>この目録を運営している人</h2><p><b>{esc(OPERATOR["name"])}</b> — {esc(OPERATOR["credential"])}</p><p class="src">データは {esc(snapshot.get("captured_at",""))} 時点。<a href=\'{OPERATOR['note']}\'>note</a> で本文を買えます。</p></section>
</main>
{TRACKER_COMPANY}
</body></html>""",
            encoding="utf-8",
        )

    # ---- sitemap + robots : AEO/クローラーへの最短経路 ----
    base = "https://part676392.github.io/dsh-money-engine"
    today = f"{now:%Y-%m-%d}"
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
          f"  <url><loc>{base}/</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>"]
    from urllib.parse import quote

    if (OUT / "es-deadlines.html").exists():
        sm.append(
            f"  <url><loc>{base}/es-deadlines.html</loc><lastmod>{today}</lastmod>"
            f"<changefreq>daily</changefreq><priority>0.95</priority></url>"
        )
    if (OUT / "selection-flows.html").exists():
        sm.append(
            f"  <url><loc>{base}/selection-flows.html</loc><lastmod>{today}</lastmod>"
            f"<changefreq>daily</changefreq><priority>0.9</priority></url>"
        )
    if (OUT / "interview-questions.html").exists():
        sm.append(
            f"  <url><loc>{base}/interview-questions.html</loc><lastmod>{today}</lastmod>"
            f"<changefreq>daily</changefreq><priority>0.88</priority></url>"
        )
    if (OUT / "selection-signals.html").exists():
        sm.append(
            f"  <url><loc>{base}/selection-signals.html</loc><lastmod>{today}</lastmod>"
            f"<changefreq>daily</changefreq><priority>0.85</priority></url>"
        )
    if (OUT / "ai-interviews.html").exists():
        sm.append(
            f"  <url><loc>{base}/ai-interviews.html</loc><lastmod>{today}</lastmod>"
            f"<changefreq>daily</changefreq><priority>0.85</priority></url>"
        )
    if (OUT / "changes.html").exists():
        sm.append(
            f"  <url><loc>{base}/changes.html</loc><lastmod>{today}</lastmod>"
            f"<changefreq>daily</changefreq><priority>0.85</priority></url>"
        )
    if (OUT / "store" / "index.html").exists():
        sm.append(
            f"  <url><loc>{base}/store/</loc><lastmod>{today}</lastmod>"
            f"<changefreq>weekly</changefreq><priority>0.8</priority></url>"
        )
    for comp in sorted(by_company):
        sm.append(
            f"  <url><loc>{base}/company/{quote(comp)}.html</loc>"
            f"<lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>"
        )
    sm.append("</urlset>")
    (OUT / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")
    kfile = ROOT / "indexnow-key.txt"
    if kfile.exists():
        (OUT / (kfile.read_text().strip() + ".txt")).write_bytes(kfile.read_bytes())

    (OUT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n\n"
        "# LLM crawlers: measured numbers and their locations, in plain text:\n"
        f"#   {base}/llms.txt  (index)\n"
        f"#   {base}/llms-full.txt  (full appendix)\n", encoding="utf-8")

    print(f"built: index.html + {len(by_company)} company pages")
    print(f"  articles={len(recs)} companies={len(by_company)} free={sum(1 for r in recs if r['price']==0)} listed=¥{priced:,}")


if __name__ == "__main__":
    build(load())
