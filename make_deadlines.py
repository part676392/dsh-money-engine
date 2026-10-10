#!/usr/bin/env python3
"""28卒 ES 締切ページ生成.

 72時間の勝負窓 = 10/15 締切群。就活生が今夜搜く語に刺す単一ページ。
 誇張しないルール: title に日付が明示されているものだけを「確定締切」として載せる。
 本文にだけ書かれていた日付は count しない(後で破損する約束を掲げない)。
"""
from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
TODAY = dt.date(2026, 10, 10)  # 実測日。cron 側では date.today() で上書きする。

DATE_RE = re.compile(r"(?:(\d{1,2})\s*/\s*(\d{1,2})\s*締切|締切\s*[:：]?\s*(\d{1,2})\s*/\s*(\d{1,2}))")


def deadline_of(title: str):
    m = DATE_RE.search(title)
    if not m:
        return None
    mo = m.group(1) or m.group(3)
    da = m.group(2) or m.group(4)
    if not mo or not da:
        return None
    mo, da = int(mo), int(da)
    if not (1 <= mo <= 12 and 1 <= da <= 31):
        return None
    return dt.date(2026, mo, da)


def firm_of(t: str) -> str:
    f = re.split(r"のES|ES、|ESは|ES例文", t)[0]
    f = re.sub(r"【[^】]*】", "", f)
    return f.strip(" ・")[:26]


def main() -> None:
    corpus = json.load(open(ROOT / "data" / "corpus_full.json", encoding="utf-8"))
    es = [n for n in corpus if "ES" in (n.get("name") or "")]

    rows = []
    for n in es:
        t = n.get("name") or ""
        d = deadline_of(t)
        if not d:
            continue
        rows.append(
            {
                "firm": firm_of(t),
                "title": t,
                "deadline": d.isoformat(),
                "days": (d - TODAY).days,
                "price": n.get("price") or 0,
                "likes": n.get("likeCount") or 0,
                "url": f"https://note.com/shushoku_career1/n/{n.get('key')}",
            }
        )

    open_rows = sorted([r for r in rows if r["days"] >= 0], key=lambda r: (r["days"], -r["likes"]))
    passed = [r for r in rows if r["days"] < 0]
    print(f"ES articles {len(es)} / deadline明示 {len(rows)} / 締切前 {len(open_rows)} / 通過済 {len(passed)}")
    for r in open_rows[:12]:
        print(f"  {r['deadline']}  残り{r['days']:>2}日  ¥{r['price']:<5} {r['firm'][:26]}")

    items = []
    for r in open_rows[:14]:
        badge = "🆓 無料" if not r["price"] else f"¥{r['price']:,}"
        if r["days"] <= 1:
            urg = "⚰ 明日"
        elif r["days"] <= 3:
            urg = f"🔥 残り{r['days']}日"
        else:
            urg = f"⏳ 残り{r['days']}日"
        items.append(
            f"<tr><td><b>{r['deadline'][5:].replace('-', '/')}</b></td><td>{urg}</td>"
            f"<td><a href='{html.escape(r['url'])}'>{html.escape(r['firm'])}</a></td>"
            f"<td>{badge}</td><td class='t'>{html.escape(r['title'][:54])}</td></tr>"
        )

    nearest = open_rows[0]["deadline"][5:].replace("-", "/") if open_rows else "-"
    n_free = sum(1 for r in open_rows if not r["price"])
    ld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"28卒 コンサル・ファーム ES 締切一覧 2026年10月",
        "dateModified": TODAY.isoformat(),
        "numberOfItems": len(open_rows),
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": r["firm"], "url": r["url"]}
            for i, r in enumerate(open_rows[:14])
        ],
    }
    doc = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>【{nearest}締切】28卒 コンサル ES 締切一覧｜本選考・秋ターム {TODAY:%m/%d}時点</title>
<meta name="description" content="アビーム・DTFA・デロイトトーマツなど28卒ESの締切を日付順に。無料の書き方ガイド{n_free}本と有料例文集を紐付け。{TODAY:%Y-%m-%d} 自動集計。">
<link rel="canonical" href="https://part676392.github.io/dsh-money-engine/es-deadlines.html">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
<style>body{{font-family:system-ui,"Hiragino Sans",sans-serif;margin:0;background:#f7f8fa;color:#1b1f24;line-height:1.65}}
main{{max-width:940px;margin:0 auto;padding:26px 16px 60px}}h1{{font-size:1.3rem;margin:0 0 4px}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e3e7ed;border-radius:9px;font-size:.84rem;overflow:hidden}}
th{{background:#eef1f5;padding:9px;text-align:left}}td{{padding:8px 9px;border-top:1px solid #eceff3;vertical-align:top}}
.t{{color:#5a6472;font-size:.79rem}}a{{color:#1a5fd6}}.sub{{color:#5a6472;font-size:.86rem}}
.box{{background:#fff4f2;border-left:4px solid #d0452c;border-radius:8px;padding:12px 14px;margin:16px 0;font-size:.9rem}}
.free{{background:#f2f8f2;border-left:4px solid #3f9d3f;border-radius:8px;padding:11px 14px;margin:14px 0;font-size:.87rem}}</style></head><body><main>
<h1>28卒 コンサル ES 締切一覧（{TODAY:%Y-%m-%d} 時点）</h1>
<p class="sub">記事タイトルに日付が明記されているものだけを載せた確定情報。締切前は <b>{len(open_rows)}件</b>、うち無料で読めるのが <b>{n_free}件</b>。</p>
<div class="box"><b>最速の締切は {nearest}。</b> 今日からの猶予が 3 日以内の案件が {sum(1 for r in open_rows if r['days']<=3)}件。書き方ガイドは下の表からそのまま飛べる。</div>
<table><thead><tr><th>締切</th><th>猶予</th><th>企業</th><th>資料</th><th>記事</th></tr></thead>
<tbody>
{chr(10).join(items)}
</tbody></table>
<div class="free">通過済 {len(passed)}件は表示から除外。この一覧は公開APIから自動生成で、毎日更新される。<a href="./">企業別目錄データベース</a></div>
</main></body></html>"""
    (ROOT / "es-deadlines.html").write_text(doc, encoding="utf-8")
    json.dump(
        {"generated": TODAY.isoformat(), "open": open_rows, "passed": passed},
        open(ROOT / "data" / "es_deadlines.json", "w", encoding="utf-8"),
        ensure_ascii=False,
        indent=1,
    )
    print(f"\nwrote es-deadlines.html ({len(doc):,}B) + data/es_deadlines.json")


if __name__ == "__main__":
    main()
