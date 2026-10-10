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
import json
import pathlib
import re
import datetime as dt

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "site"
DATA = ROOT / "data"


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


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
    html_doc = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>転職・新卒 選考対策 目録データベース｜{len(recs)}本を企業別に横断検索</title>
<meta name="description" content="{len(recs)}本の面接対策・ES資料を企業別に検索。無料/有料の内訳と公開日を毎日自動更新。">
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
input{{width:100%;padding:10px;border:1px solid #cfd6df;border-radius:8px;font-size:.95rem;margin:16px 0 4px;box-sizing:border-box}}
.note{{font-size:.78rem;color:#6b7480;margin-top:22px;border-top:1px solid #e3e7ed;padding-top:12px}}
code{{background:#eef1f5;padding:1px 5px;border-radius:4px;font-size:.85em}}
</style></head><body><main>
<h1>転職・新卒 選考対策 目録データベース</h1>
<p class="sub">志望企業の面接対策資料が「あるか無いか」を即答する検索窓。<b>{snapshot['captured_at']}</b> 時点・毎日自動更新</p>
<div class="cards">
<div class="c"><b>{len(recs)}</b><span>登録資料</span></div>
<div class="c"><b>{len(by_company)}</b><span>カバー企業</span></div>
<div class="c"><b>{sum(1 for r in recs if r['price']==0)}</b><span>無料で読める</span></div>
<div class="c"><b>¥{priced:,}</b><span>掲載総額</span></div>
</div>
<p class="sub">{kinds}</p>
<input id="q" placeholder="企業名を入力（例: イオン銀行 / アビーム / NTT東日本）" oninput="f()">
<table id="t"><thead><tr><th>企業</th><th>資料数</th><th>無料</th><th>有料</th><th>選考種別</th><th>最新</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody></table>
<p class="note">出典: <a href="https://note.com/shushoku_career1">note / 転職ナビ・中途キャリアの研究所</a> 公開API。機械可読データは <a href="data/snapshot-latest.json">data/snapshot-latest.json</a>、日次履歴は <code>data/history/</code> に蓄積。変化の履歴そのものが再取得不能な資産になる設計。</p>
</main><script>
function f(){{var v=document.getElementById('q').value.toLowerCase();
document.querySelectorAll('#t tbody tr').forEach(function(r){{
r.style.display=!v||r.textContent.toLowerCase().includes(v)?'':'none';}});}}
</script></body></html>"""
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
        (cdir / f"{comp}.html").write_text(
            f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(comp)}の面接対策資料 {len(g)}点（無料{len(free)}/有料{len(paid)}）｜選考DB</title>
<meta name="description" content="{esc(q)}">
<script type="application/ld+json">{json.dumps(ltd, ensure_ascii=False)}</script>
<style>body{{font-family:system-ui,"Hiragino Sans",sans-serif;margin:0;background:#f7f8fa;color:#1b1f24;line-height:1.7}}
main{{max-width:760px;margin:0 auto;padding:26px 16px 60px}}h1{{font-size:1.25rem}}
li{{margin:9px 0}}.p{{font-size:.75rem;background:#e8f0ff;color:#1a4fa0;padding:1px 7px;border-radius:20px;margin-left:6px}}
.d{{font-size:.75rem;color:#6b7480;margin-left:6px}}a{{color:#1a5fd6}}</style></head><body><main>
<p><a href="../">← 目録データベースへ</a></p>
<h1>{esc(comp)} の選考対策資料 {len(g)}点</h1>
<p>{esc(q)} 選考種別：{esc('、'.join(kinds_here))}。</p>
<ul>{chr(10).join(items)}</ul>
</main></body></html>""",
            encoding="utf-8",
        )

    print(f"built: index.html + {len(by_company)} company pages")
    print(f"  articles={len(recs)} companies={len(by_company)} free={sum(1 for r in recs if r['price']==0)} listed=¥{priced:,}")


if __name__ == "__main__":
    build(load())
