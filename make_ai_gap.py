#!/usr/bin/env python3
"""AI・録上面接の検索需要だけで作る受け口.

 動機: 「キユーピー 録画 面接」のような語で検索が起きている (autocomplete 実測)。
 なのにこの目録側では会社ページ内の小ブロックに仕舞っていて、
 その語で飛んでくる着地頁が無かった。

 正直さの約束:
   - 観測したのは「検索が起きていること」だけ。企業が実際に AI 面接を
     実施するかは、このデータからは確定できないと全ページに書く。
   - 実施・非実施を断定する文を入れない。断言検証を機械で通す。
"""
from __future__ import annotations

from tracker_js import tracker
import buy_block
BUY = buy_block.html()
import datetime as dt
import html
import json
import pathlib
import re
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "ai-interviews.html"
SITE = "https://part676392.github.io/dsh-money-engine"
DEMAND = ROOT / "data" / "ai_interview_demand.json"
GAP = ROOT / "data" / "ai_gap_audit.json"
SRC = ROOT / "data" / "ai_verified_sources.json"


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


# 断言してはいけない語 (実施を事実として述べる表現)。
# 疑問文 ("実施していますか") は許す。過去に禁止語を雑に文字列照合して
# FAQ の見出しを弾いた誤検出があるため、語尾で区別する。
BANNED_PATTERNS = [
    re.compile(r"実施しています(?!か)"),
    re.compile(r"実施している(?!か|。)"),
    re.compile(r"導入しています(?!か)"),
    re.compile(r"採用しています(?!か)"),
    re.compile(r"全社で実施"),
]


def load() -> tuple:
    dem = json.loads(DEMAND.read_text(encoding="utf-8")) if DEMAND.exists() else {}
    gap = json.loads(GAP.read_text(encoding="utf-8")) if GAP.exists() else {}
    return dem, gap


def coverage(company: str) -> dict:
    """その会社の会社ページに AI ブロックが実在するかを HTML から確かめる."""
    fn = ROOT / "company" / f"{company}.html"
    if not fn.exists():
        # 名前に全角括弧などを含む社がある
        cands = list((ROOT / "company").glob(f"{company}*.html"))
        if not cands:
            return {"page": None, "has_block": False}
        fn = cands[0]
    h = fn.read_text(encoding="utf-8", errors="replace")
    return {"page": fn.name, "has_block": ("録上面接" in h or "AI 面接" in h or "AI面接" in h)}


def assert_check(doc: str) -> list:
    bad = []
    for pat in BANNED_PATTERNS:
        m = pat.search(doc)
        if m:
            i = m.start()
            bad.append(f"{m.group(0)} «…{doc[max(0,i-18):i+14]}…»")
    return bad


H2 = ('<h2 style="font-size:.98rem;margin:26px 0 8px;'
      'border-bottom:1px solid #ddd8cf;padding-bottom:5px">')


def source_block() -> str:
    """導入を裏取る発表が実際に取れた社だけを出す.

    発表の主体 (企業自身かベンダー側か) を必ず列に書く。
    「実施しています」の断定を避け、取れた文書そのものを見せる形にする。
    """
    if not SRC.exists():
        return (H2 + "実施を裏取る発表</h2><p style=\"font-size:.88rem\">"
                "現時点で、この一覧の企業について導入を裏取る発表を取れていません。</p>")
    raw = json.loads(SRC.read_text(encoding="utf-8"))
    srcs = raw if isinstance(raw, list) else [raw]
    if not srcs:
        return (H2 + "実施を裏取る発表</h2><p style=\"font-size:.88rem\">"
                "現時点で、この一覧の企業について導入を裏取る発表を取れていません。</p>")
    rows = []
    for x in srcs:
        rows.append(
            "<tr><td>" + esc(x.get("company")) + "</td>"
            "<td>" + esc(x.get("title")) + "</td>"
            "<td>" + esc(x.get("publisher")) + "</td>"
            "<td>" + esc(x.get("date")) + "</td>"
            + '<td><a href="' + esc(x.get("url"))
            + '" rel="nofollow noopener">発表</a></td></tr>'
        )
    return (
        H2 + "実施を裏取る発表</h2>"
        "<p style=\"font-size:.88rem\">上の表とは別に、<strong>導入を述べる文書が実際に取得できた企業"
        "</strong>をここに置きます。ここにある社だけは「確定できない」の側ではありません。"
        "ただし発表の主体（企業自身か、ツールを提供する側か）を列に書いてあるので、"
        "読む前にそこを確認してください。</p>"
        "<table><thead><tr><th>企業</th><th>発表タイトル</th><th"
        ">発表元</th><th>日付</th><th></th></tr></thead><tbody>"
        + "\n".join(rows) + "</tbody></table>"
    )


def main() -> int:
    dem, gap = load()
    if not dem:
        print("  data/ai_interview_demand.json が空")
        return 0

    rows = []
    with_block = 0
    for comp in sorted(dem):
        terms = dem[comp]
        cov = coverage(comp)
        if cov["has_block"]:
            with_block += 1
        term_html = " ".join(f"<code>{esc(t)}</code>" for t in terms[:6])
        link = (f'<a href="company/{urllib.parse.quote(cov["page"])}">会社ページ</a>'
                if cov["page"] else "—")
        rows.append(
            f"<tr><td>{esc(comp)}</td><td>{len(terms)}</td>"
            f"<td>{term_html}</td>"
            f"<td>{'有' if cov['has_block'] else '無'}</td><td>{link}</td></tr>"
        )

    n = len(dem)
    total_terms = sum(len(v) for v in dem.values())
    today = dt.date.today().isoformat()
    checked = gap.get("checked_articles", "—")
    mention = gap.get("articles_mentioning", "—")
    covered = gap.get("companies_covered", "—")

    faq = json.dumps({
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question",
             "name": "この一覧の企業は AI 面接を実施していますか",
             "acceptedAnswer": {"@type": "Answer", "text": (
                 "この頁が観測しているのは、企業名と「AI 面接」「録画 面接」を組み合わせた"
                 "検索語が実際に発生しているという事実だけです。企業側が実施しているかは、"
                 "このデータからは確定できません。")}},
            {"@type": "Question",
             "name": "検索語はどうやって集めましたか",
             "acceptedAnswer": {"@type": "Answer", "text": (
                 "主要検索エンジンのキーワード候補 (autocomplete) を機械的に収集し、"
                 "企業名を含む語だけを正規化して残しました。人手による推測は入れていません。")}},
            {"@type": "Question",
             "name": "AI 面接に備えて何が出来ますか",
             "acceptedAnswer": {"@type": "Answer", "text": (
                 "録画形式は設問が事前に分かることが多く、同じ設問への回答を反復して"
                 "時間内に収められる形にしておくことが有効です。実演回数と所要時間は"
                 "当社目録の収録データ側に記録しています。")}},
        ],
    }, ensure_ascii=False, indent=1)

    ld = json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "AI・録上面接に関する検索需要の観測一覧",
        "description": (f"{n} 社について企業名込みで観測した AI・録上面接系の検索語 "
                        f"{total_terms} 件の実測。実施有無の断定は含まない。"),
        "creator": {"@type": "Person", "name": "転職ナビ・中途キャリアの研究所"},
        "url": f"{SITE}/ai-interviews.html",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "creditText": "CC BY 4.0 は抽出した表・順序・対応づけにだけ適用します。本文の著作権は note の各記事の著者に帰属し、引用は出典URLつきで最小限に留めています。",
        "isBasedOn": "https://note.com/shushoku_career1",
    }, ensure_ascii=False, indent=1)

    doc = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI・録上面接で検索されている企業 {n} 社 — 検索語 {total_terms} 件の実測 | 目録</title>
<meta name="description" content="企業名とAI面接・録画面接を組み合わせた検索語 {total_terms} 件を、{n} 社について機械収集した一覧。実施有無は断定しません。">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{SITE}/ai-interviews.html">
<script type="application/ld+json">
{ld}
</script>
<script type="application/ld+json">
{faq}
</script>
<style>
body{{font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif;margin:0;background:#f6f5f2;color:#1d1c1a;line-height:1.7}}
main{{max-width:940px;margin:0 auto;padding:30px 18px 70px}}
h1{{font-size:1.3rem;margin:0 0 6px}}
.sub{{color:#6d675e;font-size:.88rem;margin:0 0 18px}}
.caution{{background:#fff6e8;border:1px solid #e7cf9f;border-radius:8px;padding:12px 15px;font-size:.88rem;margin:16px 0 22px}}
table{{width:100%;border-collapse:collapse;font-size:.84rem}}
th,td{{text-align:left;padding:7px 8px;border-bottom:1px solid #e6e1d8;vertical-align:top}}
th{{background:#efeee9;font-weight:600}}
code{{background:#eceae4;padding:1px 5px;border-radius:4px;font-size:.76rem;margin:0 3px 3px 0;display:inline-block}}
a{{color:#7a5230}}
.note{{font-size:.8rem;color:#6d675e;margin-top:24px}}
</style></head><body><main>
<h1>AI・録上面接で検索されている企業 {n} 社</h1>
<p class="sub">企業名と「AI 面接」「録画 面接」「動画 面接」を組み合わせる検索が、実際にいくつ起きているか。機械収集した {total_terms} 件の実一覧です。</p>

<div class="caution">
<strong>この頁が言えることと言えないこと。</strong><br>
言えるのは「その検索語を誰かが入力している」という事実だけです。
<strong>掲載企業が実際に AI 面接・録上面接を実施するかは、このデータからは確定できません。</strong>
実施の有無は各社の採用ページと当日の案内で確認してください。
</div>

<table>
<thead><tr><th>企業</th><th>観測語</th><th>実際に拾った検索語</th><th>会社ページの<br>AI節</th><th>関連</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody></table>

{source_block()}

<h2 style="font-size:.98rem;margin:26px 0 8px;border-bottom:1px solid #ddd8cf;padding-bottom:5px">被覆の現実</h2>
<p style="font-size:.88rem">目録に収めた記事 {checked} 本を機械走査した結果、AI 面接に触れていたのは {mention} 本、
それは {covered} 社分だけでした（表の「会社ページのAI節」は需要語から自動生成した節の数で、記事本文の記述ではありません。この頁が問題にしているのは本文側の被覆です）。<strong>{n} 社分の需要に対して、受け口が圧倒的に足りない</strong>のが実測です。
この頁はそこを埋めるために、需要側だけで作りました。</p>

<p class="note"><b>権利の範囲:</b> CC BY 4.0 は抽出した表・順序・対応づけにだけ適用します。本文の著作権は note の各記事の著者に帰属し、この頁にあるのは出典URLつきの最小限の引用です。<br>更新: {today}　収集: 主要検索エンジンのキーワード候補を正規化して企業名を含む語のみ抽出。人手の推測は含みません。<br>
他の観測の積み上がりは <a href="changes.html">運用履歴</a> に公開しています。</p>
{tracker("ai")}{BUY}</main></body></html>"""

    bad = assert_check(doc)
    if bad:
        raise SystemExit(f"断言が混入したので公開しません: {bad}")
    OUT.write_text(doc, encoding="utf-8")
    print(f"  wrote ai-interviews.html ({len(doc):,} bytes)")
    print(f"  companies={n} terms={total_terms} 目録内にAI項を持つ社={with_block} 断言検査=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
