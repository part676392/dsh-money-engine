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

import buy_block
BUY = buy_block.html()
import collections
import html
import urllib.parse
import json
import pathlib
import subprocess
import re
import datetime as dt

import demand
import order_link
from tracker_js import beacon_js, tracker

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT
DATA = ROOT / "data"


def _dj(fn: str) -> dict:
    try:
        return json.loads((DATA / fn).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def abacus_counts() -> dict:
    """访问計は external。落ちても履歴を止めない (取れなければ鍵ごと省く)。"""
    out = {}
    for k in ("home", "store", "license", "sample", "mini", "lineup", "reverse"):
        try:
            r = subprocess.run(["curl", "-s", "--max-time", "8",
                                f"https://abacus.jasoncameron.dev/get/dsh-money-engine/{k}"],
                               capture_output=True, text=True, timeout=14)
            v = json.loads(r.stdout).get("value")
            if isinstance(v, int):
                out[k] = v
        except Exception:  # noqa: BLE001
            pass
    return out


def history_record(snap: dict, loc: str) -> dict:
    """history が 5 鍵しか積んでいなかった (2026-10-11 実測)。
    後から取り直せないもの — 访问・受注・抽出量 — を同じ series に積む。"""
    q, fl, sg = _dj("interview_questions.json"), _dj("selection_flows.json"), _dj("selection_signals.json")
    ln, rv = _dj("question_lineups.json"), _dj("reverse_questions.json")
    dl, dv = _dj("es_deadlines_strict.json"), _dj("deliveries.json")
    # deliveries.json は id 辞書。orders_total の様な集計鍵は無い (実測で null になった)。
    dvi = list(dv.values()) if isinstance(dv, dict) else (dv or [])
    n_rehearsal = sum(1 for x in dvi if str(x.get("kind", "")) == "rehearsal")
    # 閉結 (送金なし) は注文として数えない (gh issue を消すと実注文が永久に残っていた)。
    n_closed = sum(1 for x in dvi if "閉結" in str(x.get("status", "")))
    n_delivered = sum(1 for x in dvi if "delivered" in str(x.get("status", "")).lower()
                      or "納品" in str(x.get("status", "")))
    cnt = abacus_counts()
    rows = sum(len(l.get("order") or []) for o in (ln.get("per_company") or {}).values()
               for l in o.get("lineups") or [])
    return {
        "captured_at": snap.get("captured_at"), "location": loc,
        "articles": snap.get("articles"), "companies": snap.get("companies"),
        "listed_value_yen": snap.get("listed_value_yen"), "by_kind": snap.get("by_kind"),
        "questions": q.get("questions_total"), "questions_raw": q.get("questions_extracted_raw"),
        "companies_with_questions": q.get("companies_with_questions"),
        "flows": fl.get("flows_total"),
        "signals": sum((sg.get("stage_totals") or {}).values()),
        "lineup_rows": rows, "lineup_companies": ln.get("companies"),
        "lineup_modal_pct": ln.get("modal_exact_pct"),
        "reverse_quotes": rv.get("quotes"), "reverse_companies": rv.get("companies"),
        "deadlines_open": len(dl.get("open") or []) if isinstance(dl, dict) else None,
        "orders_real": len(dvi) - n_rehearsal - n_closed, "orders_rehearsal": n_rehearsal,
        "orders_closed": n_closed,
        "delivered": n_delivered,
        "traffic": cnt, "traffic_total": sum(cnt.values()),
        "cash_usd": 0, "cash_eth": 0,
    }


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


OPERATOR = {
    "name": "転職ナビ・中途キャリアの研究所",
    "credential": "元人事の採用担当。書類選考から最終面接まで、数多くの候補者を評価してきた「選ぶ側」の視点。",
    "note": "https://note.com/shushoku_career1",
}



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
    # 企業頁に載せる追加資産 (question_lineups / reverse_questions)。data を読むだけで手書きしない。
    def _loadj(fn):
        fp = DATA / fn
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    LNU = _loadj("question_lineups.json").get("per_company") or {}
    RVQ = _loadj("reverse_questions.json").get("per_company") or {}
    # 質問の実文 (小見出しを落とした形)。企業頁で「社名 面接 質問」の答えにする。
    IQ = _loadj("interview_questions.json").get("per_company") or {}

    # 名前ゆれで同じ会社の頁が分裂していた (実測: JR西日本が4頁、先頭が全角スペースの名前8件、
    # 491 頁 -> 束ねると 479 社)。機械で束ね、割っていた名前の URL は canonical への連絡頁に残す。
    from company_names import canon_map
    CMAP, ALIAS = canon_map(list(by_company) + list(LNU) + list(RVQ) + list(IQ))

    def _merge_lists(d):
        out = collections.defaultdict(list)
        for k, v in d.items():
            out[CMAP.get(k, k)].extend(v or [])
        return out

    def _merge_best(d):
        out = {}
        for k, v in d.items():
            ck = CMAP.get(k, k)
            have = len((out.get(ck) or {}).get("lineups") or [])
            if ck not in out or len((v or {}).get("lineups") or []) > have:
                out[ck] = v
        return out

    by_company = collections.defaultdict(list, _merge_lists(by_company))
    IQ = _merge_lists(IQ)
    RVQ = _merge_lists(RVQ)
    LNU = _merge_best(LNU)

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
    # dev と runner が同じ YYYY-MM-DD.json に追記して衝突した (2026-10-11 実測)。
    # 履歴は堀なので片方を捨てられない。場所ごとに分けて同名衝突を無くす。
    loc = "runner" if "/dsh-runner/" in str(ROOT) else "dev"
    rec = history_record(snapshot, loc)
    (hist / f"{now:%Y-%m-%d}.{loc}.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    # 日付 file は同じ日の再実行で上書きされる (実測: 4 回走っても file は 3 個のまま)。
    # 走った分の-series を捨てないために、場所ごとに追記専用の背骨を置く。
    # data/history/ は merge=generated 対象外 (check-attr で unspecified を確認済み) なので
    # 両側の行が消えない。
    with open(hist / f"runs.{loc}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

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
            f"<tr><td><a href='company/{urllib.parse.quote(comp)}.html'>{esc(comp)}</a>"
            + (f"<span style='color:#6b7480;font-size:.78rem'> (別名: {esc('、'.join(ALIAS.get(comp, [])[:2]))}</span>"
               if ALIAS.get(comp) else "") + "</td>"
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
<a class="dead" href="data-license.html">💴 <b>データ資産の購入</b> — 必要な企業群だけ切り出した CSV を公開URLで納品。現行 CSV はそのまま無料</a>
<a class="dead" href="deliveries.html">📦 <b>納品一覧</b> — 注文が進んだ分だけを積む記録（今は0件）</a>
<a class="dead" href="question-lineups.html">🧩 <b>面接の質問カテゴリの並び順</b> — 467社ぶん構造化。64%が完全に同一の10カテゴリ順で、逆質問は常に最後</a>
<a class="dead" href="reverse-questions.html">🔁 <b>逆質問の実文</b> — 本文に起きた文だけ。24文/8社 (薄いので薄いと書いてある)</a>
<a class="dead" href="sample.html">📄 <b>納品物見本</b> — 有料で届く CSV の実物を3社ぶん公開（面接質問105問・公式フロー10本）</a>
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

{BUY}</main><script>
function f(){{var v=document.getElementById('q').value.toLowerCase();
document.querySelectorAll('#t tbody tr').forEach(function(r){{
r.style.display=!v||r.textContent.toLowerCase().includes(v)?'':'none';}});}}
</script>{TRACKER_HOME}</body></html>"""
    (OUT / "index.html").write_text(html_doc, encoding="utf-8")

    # ---- 404 : 見失った人を目録に戻す (GitHub 既定の 404 だと資産の名前も値段も消える) ----
    q4 = _dj("interview_questions.json")
    f4 = _dj("selection_flows.json")
    l4 = _dj("question_lineups.json")
    h4 = _dj("history/index.json")
    n_q4 = f"{int(q4.get('questions_total') or 0):,}"
    # 1,779 は行数。同じ文が複数社に付くので、実文の数は別に出す (実測: 最多の1文が500行)
    n_d4 = f"{int(q4.get('questions_distinct_text') or 0):,}"
    n_f4 = f"{int(f4.get('flows_total') or 0)}"
    # rows と言う鍵は無い (実測で KeyError 回避のフォールバックが 467 = 社数を返していた)。
    # 行数は history_record と同じ数え方を用いる (exports の CSV と一致する)。
    n_l4 = f"{sum(len(l.get('order') or []) for o in (l4.get('per_company') or {}).values() for l in o.get('lineups') or []):,}"
    n_h4 = f"{int(h4.get('observations') or 0)}"
    c4 = int(snapshot.get("companies") or 0)
    nav404 = [("index.html", f"企業別の目録トップ ({c4} 社)"),
              ("interview-questions.html", f"面接質問 {n_q4} 行（重複を除いた実文 {n_d4}）"),
              ("question-lineups.html", f"質問カテゴリの並び順 {n_l4}"),
              ("selection-flows.html", f"公式選考フロー {n_f4} 本"),
              ("sample.html", "納品物見本（3社ぶんの実物）"),
              ("data-license.html", "データ資産の購入（1社だけ $5 から）"),
              ("exports/manifest.csv", "CSV 一覧と列の定義"),
              ("changes.html", f"運用履歴（観測 {n_h4} 件）"),
              ("store/", "執筆物の注文")]
    err_doc = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>その頁は見つかりません｜転職・新卒 選考対策 目録データベース</title>
<meta name="description" content="アドレスが古いか打ち間違いです。{c4} 社の目録、面接質問 {n_q4} 行（実文 {n_d4}）、CSV 一式はここから入れます。">
<meta name="robots" content="noindex,follow">
{tracker("404")}
<style>
body{{font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif;margin:0;background:#f7f8fa;color:#1b1f24}}
main{{max-width:760px;margin:0 auto;padding:44px 20px 80px}}
h1{{font-size:1.3rem;margin:0 0 8px}} p.why{{color:#5d6570;font-size:.92rem;margin:0 0 22px}}
ul{{list-style:none;padding:0;margin:0;border-top:1px solid #e3e6ea}}
li{{border-bottom:1px solid #e3e6ea}}
a{{display:block;padding:13px 4px;color:#2547c9;text-decoration:none;font-size:.97rem}}
a:hover{{text-decoration:underline}}
small{{display:block;color:#5d6570;margin-top:26px;font-size:.8rem;line-height:1.7}}
</style></head><body><main>
<h1>その頁は見つかりません</h1>
<p class="why">アドレスが古いか、打ち間違いです。中身は消えていません — 下のどれかから入ってください。</p>
<ul>
{chr(10).join(f'<li><a href="{p}">{t}</a></li>' for p, t in nav404)}
</ul>
<small>この頁は検索に出しません (noindex)。巡回は毎日 06:10 / 19:40 JST に自動で走り、
上の数字はそのときに取り直した実測です。</small>
</main></body></html>"""
    (OUT / "404.html").write_text(err_doc, encoding="utf-8")

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
        o = LNU.get(comp) or {}
        lu = (o.get("lineups") or [{}])[0].get("order") or []
        if lu:
            seq = " \u2192 ".join(esc(x) for x in lu)
            cln = (f"<div class='cd'><h3>質問カテゴリの並び (記事の目次から構造化)</h3>"
                   f"<p style='font-size:.88rem'>{seq}</p>"
                   f"<p class='raw'>この会社で構造化した羅列 {len(o.get('lineups') or [])} 本 ／ "
                   f"全社の一覧: <a href='/dsh-money-engine/question-lineups.html'>質問カテゴリの並び順</a> ／ "
                   f"自社の行: <a href='/dsh-money-engine/exports/question_lineups.csv'>question_lineups.csv</a></p></div>")
        else:
            cln = ""
        rv = (RVQ.get(comp) or [])
        if rv:
            cln += (f"<div class='cd'><h3>逆質問にふれる本文の実文</h3><ul>"
                    + "".join(f"<li>「{esc(it['quote'][:180])}」 <a href='{esc(it['url'])}'>出典</a></li>"
                              for it in rv[:3])
                    + f"</ul><p class='raw'>全社: <a href='/dsh-money-engine/reverse-questions.html'>逆質問の実文</a></p></div>")
        iqr = IQ.get(comp) or []
        uniq, seen = [], set()
        for it in iqr:
            t = (it.get("question") or "").strip()
            if t and t not in seen:
                seen.add(t)
                uniq.append(it)
        if uniq:
            cats = {}
            for it in uniq:
                k = it.get("category") or "未判定"
                cats[k] = cats.get(k, 0) + 1
            cat_txt = "、".join(f"{k} {v}" for k, v in sorted(cats.items(), key=lambda x: -x[1]))
            qrows = "".join(
                "<tr><td>" + esc(it.get("category") or "未判定") + "</td><td>「"
                + esc((it.get("question") or "")[:150]) + "」</td><td>"
                + esc((it.get("intent") or "—")[:90]) + "</td><td><a href='"
                + esc(it.get("url") or "#") + "'>出典</a></td></tr>"
                for it in uniq[:12])
            if len(uniq) < len(iqr):
                dup = ("収録 " + f"{len(iqr):,}" + " 行のうち、この会社で同じ文の行をまとめると "
                       + f"{len(uniq):,}" + " 文です（" + f"{len(iqr) - len(uniq):,}"
                       + " 行が同じ文の繰り返し）。")
            else:
                dup = ("収録 " + f"{len(iqr):,}" + " 行は、この会社では重複なく " + f"{len(uniq):,}" + " 文です。")
            cln += ("<div class='cd'><h3>面接で投げられた質問の実文 " + f"{len(uniq):,}"
                    + " 文（収録 " + f"{len(iqr):,}" + " 行）</h3>"
                    + "<p class='raw'>" + dup
                    + "小見出しを落とした形で、カテゴリは機械が振りました (迷った行は 未判定)。全量: "
                    + "<a href='/dsh-money-engine/exports/interview_questions.csv'>interview_questions.csv</a> ／ "
                    + "<a href='/dsh-money-engine/interview-questions.html'>全社一覧</a></p>"
                    + "<table class='qt'><thead><tr><th>カテゴリ</th><th>質問の実文</th>"
                    + "<th>面接官の意図 (記事に書いた範囲)</th><th>出典</th></tr></thead><tbody>"
                    + qrows + "</tbody></table></div>")
        else:
            uniq = []
            cln += ("<div class='cd'><h3>面接で投げられた質問の実文</h3>"
                    "<p class='raw'>この会社については、質問の実文をまだ収録できていません。"
                    "上の資料リンクの中に出ている可能性はありますが、空欄を埋めるために文は作っていません。"
                    "全社の一覧: <a href='/dsh-money-engine/interview-questions.html'>面接質問の実文</a></p></div>")
        # 金の入口: 企業頁から会社名を書かずに注文できる (prefill の鍵は form の id)。
        buy_url = esc(order_link.url(comp, order_link.ENTRY_PLAN))
        n_txt = f"質問実文 {len(uniq):,} 文" if uniq else "この会社の質問実文は未収録"
        cln += ("<p class='buywrap'><a class='buy' href='" + buy_url + "' onclick=\"" +
                beacon_js("order-click") + ";return true\">この会社ぶんを <b>$5</b> で受け取る</a>"
                "<span class='raw'> " + n_txt + "・出典URLつき。開いた注文 form には会社名が既に入っています。"
                + "注文には GitHub のアカウントがいります。</span></p>")

        # demand は収録時の名前で引くので、束ねる前の名前も順に試す (無いものを無いと言わない)。
        names_try = [comp] + list(ALIAS.get(comp) or [])

        def _try(fn):
            for nm in names_try:
                v = fn(nm)
                if v:
                    return v
            return "" if fn is not demand.ai_demand else []

        cdem = _try(lambda nm: demand.company_block(nm, dem)) if dem else ""
        cai = _try(lambda nm: demand.ai_block(nm, dem)) if dem else ""
        ai_terms = _try(lambda nm: demand.ai_demand(nm, dem)) if dem else []

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
        # 実文そのものを FAQ で返す (「{社名} 面接 質問」で搜く人への答え)。
        for it in uniq[:3]:
            nm = (it.get("question") or "").strip().rstrip("。」")
            if not nm:
                continue
            intent = (it.get("intent") or "").strip()
            ans = (intent if intent else
                   "記事に面接官の意図は書かれていません。実文と出典URLだけを収録しています。")
            ltd["mainEntity"].append({
                "@type": "Question",
                "name": f"{comp}の面接では「{nm[:120]}」と聞かれますか？",
                "acceptedAnswer": {"@type": "Answer", "text": (
                    f"収録した記事に「{(it.get('question') or '')[:180]}」という実文があります"
                    f"（カテゴリ: {it.get('category') or '未判定'}）。意図について: {ans[:200]} "
                    f"出典: {(it.get('url') or '')}")},
            })
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

        if lu:
                ltd["mainEntity"].append({
                    "@type": "Question",
                    "name": f"{comp}の面接はどの順番で聞かれますか？",
                    "acceptedAnswer": {"@type": "Answer", "text": (
                        f"収録記事の目次からは次の並びが読めます: {' → '.join(lu)}。"
                        f"これは記事が並べた順であって選考の全集ではありません。"
                        f"ただし収録 {len(LNU):,} 社ぶんの中で同じ並びが最多です。")},
                })

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
.qt{{width:100%;border-collapse:collapse;font-size:.84rem;margin-top:8px}}
.qt th,.qt td{{text-align:left;padding:6px 8px;border-bottom:1px solid #e6e1d8;vertical-align:top}}
.qt th{{background:#efeee9;font-weight:600;white-space:nowrap}}
.buywrap{{margin:16px 0 0;padding:12px;background:#fff;border:1px solid #e3e7ed;border-radius:9px}}
.buy{{display:inline-block;background:#7a5230;color:#fff;padding:8px 13px;border-radius:8px;
text-decoration:none;font-weight:600}}.buy:hover{{background:#63421f}}
.buywrap .raw{{display:inline-block;margin-left:9px}}
.d{{font-size:.75rem;color:#6b7480;margin-left:6px}}a{{color:#1a5fd6}}
.aigap{{background:#fff;border:1px solid #e3e7ed;border-left:4px solid #6b4fd6;border-radius:9px;padding:14px 16px;margin:20px 0}}
.aigap h2{{font-size:1rem;margin:0 0 6px}}.aigap p{{font-size:.86rem;margin:8px 0}}
.chips{{list-style:none;display:flex;flex-wrap:wrap;gap:6px;padding:0;margin:8px 0}}
.about{{background:#fff;border:1px solid #e3e7ed;border-left:4px solid #1a5fd6;border-radius:9px;padding:13px 15px;margin:20px 0}}
.about h2{{font-size:.95rem;margin:0 0 5px}}.about p{{font-size:.85rem;margin:6px 0}}
.src{{color:#5a6472;font-size:.79rem}}
.chips li{{margin:0;background:#f0edfd;color:#4b36a3;font-size:.78rem;padding:3px 9px;border-radius:20px}}</style></head><body><main>
<p><a href="../">← 目録データベースへ</a> CSV でも置いています: <a href="/dsh-money-engine/exports/interview_questions.csv">面接質問</a> ／ <a href="/dsh-money-engine/exports/selection_flows.csv">選考フロー</a> ／ <a href="/dsh-money-engine/exports/selection_signals.csv">選考段階</a> ／ <a href="/dsh-money-engine/exports/manifest.csv">列の定義</a>（UTF-8 BOM 付きで Excel でも日本語が化けない）　日付つき保存庫: <a href="https://github.com/part676392/dsh-money-engine/releases">GitHub Releases</a>（毎回の CSV を tag 付きで積む。ある日の数字を後から偽装できない）</p>
<h1>{esc(comp)} の選考対策資料 {len(g)}点</h1>
<p>{esc(q)} 選考種別：{esc('、'.join(kinds_here))}。</p>
<ul>{chr(10).join(items)}</ul>
{cdem}
{cai}
{cln}
<section class="about"><h2>この目録を運営している人</h2><p><b>{esc(OPERATOR["name"])}</b> — {esc(OPERATOR["credential"])}</p><p class="src">データは {esc(snapshot.get("captured_at",""))} 時点。<a href=\'{OPERATOR['note']}\'>note</a> で本文を買えます。</p></section>
</main>
{TRACKER_COMPANY}
</body></html>""",
            encoding="utf-8",
        )

    # ---- 束ねた名前の URL を殺さない: canonical への連絡頁 ----
    n_redir = 0
    for c, als in sorted(ALIAS.items()):
        cu = ("https://part676392.github.io/dsh-money-engine/company/"
              + urllib.parse.quote(c + ".html"))
        for a in als:
            (cdir / f"{a}.html").write_text(
                f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(a)}の面接対策資料は{esc(c)}の頁にまとめました</title>
<meta name="description" content="{esc(a)} は {esc(c)} と同じ会社なので、面接資料と質問実文は {esc(c)} の頁に統合しました。">
<meta name="robots" content="noindex,follow">
<link rel="canonical" href="{cu}">
<meta http-equiv="refresh" content="0; url={cu}"></head>
<body style="font-family:system-ui,'Hiragino Sans',sans-serif;margin:42px;line-height:1.8">
<p><b>{esc(a)}</b> の頁は <a href="{cu}">{esc(c)}</a> にまとめました。同じ会社の名前ゆれを機械に束ねたためです。
この URL は消さずに残しています。</p>
{TRACKER_COMPANY}</body></html>""",
                encoding="utf-8",
            )
            n_redir += 1

    # ---- sitemap + robots : AEO/クローラーへの最短経路 ----
    base = "https://part676392.github.io/dsh-money-engine"
    today = f"{now:%Y-%m-%d}"
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
          f"  <url><loc>{base}/</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>"]
    from urllib.parse import quote

    if (OUT / "deliveries.html").exists():
        sm.append(
            f"  <url><loc>{base}/deliveries.html</loc><lastmod>{today}</lastmod>"
            f"<changefreq>daily</changefreq><priority>0.7</priority></url>")
    if (OUT / "store" / "mini.html").exists():
        # 実在して noindex でもない頁が sitemap に無いと、検索は link を辿るしかない
        sm.append(
            f"  <url><loc>{base}/store/mini.html</loc><lastmod>{today}</lastmod>"
            f"<changefreq>daily</changefreq><priority>0.6</priority></url>")
    if (OUT / "sample.html").exists():
        sm.append(
            f"  <url><loc>{base}/sample.html</loc><lastmod>{today}</lastmod>"
            f"<changefreq>daily</changefreq><priority>0.8</priority></url>")
    if (OUT / "data-license.html").exists():
        sm.append(
            f"  <url><loc>{base}/data-license.html</loc><lastmod>{today}</lastmod>"
            f"<changefreq>daily</changefreq><priority>0.9</priority></url>")
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
    for extra, prio in (("question-lineups.html", "0.9"), ("reverse-questions.html", "0.8")):
        if (OUT / extra).exists():
            sm.append(
                f"  <url><loc>{base}/{extra}</loc><lastmod>{today}</lastmod>"
                f"<changefreq>daily</changefreq><priority>{prio}</priority></url>")
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
