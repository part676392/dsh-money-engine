#!/usr/bin/env python3
"""逆質問の実文を本文から抽出して頁にする.

 実測 (2026-10-11 06:42): data/full_bodies.json は 600 本 / 2,074,796 字あり、
 そのうち 553 本 (92%) に「逆質問」が現れる (出現 709)。作りながら一度も出版していなかった。
 面接対策で買い手が金を払うのはこの部分なので独立した資産にする。

 正直さ: 採るのは本文そのままの1文だけ。全文の再発行はしない (著作権は各記事の著者)。
"""
from __future__ import annotations

import csv
import html
import io
import json
import collections
import pathlib
import re
import time
from tracker_js import tracker

ROOT = pathlib.Path(__file__).resolve().parent
BASE = "https://part676392.github.io/dsh-money-engine"
OUT = ROOT / "reverse-questions.html"
DATA = ROOT / "data"
EXP = ROOT / "exports"
FULL = DATA / "full_bodies.json"

TRIG = re.compile(r"逆質問")
SPLIT = re.compile(r"(?<=[。！？!?\n])")
# 目次の羅列 ("自己PR・強み 転職理由・退職理由 … 逆質問") は 逆質問 を含むだけで中身でない。
# cell 数の分布を実測したら二峰に分かれた: 空白区切り 11 cell 以上が目次 (620 件)、
# 10 以下が散文 (51 件)。閾値を谷に置く。AI 面接で 0/37 を弾いたのと同じ罠。
CELLS_MAX = 10
ADJ = re.compile(r"逆質問[^。]{0,26}(た|し|聞|用意|準備|考え|なし|無|あ|でき|難|困|役|さ)"
                 r"|((聞|し|用意|準備|考え|出す|考える)[^。]{0,14}逆質問)")




def comp_link(name: str) -> str:
    """企業頁が実在する時だけ link。存在しない頁へ張ると audit の link 検査が落ちる (実測)。"""
    e = esc(name)
    fp = ROOT / "company" / f"{name}.html"
    return f'<a href="company/{e}.html">{e}</a>' if fp.exists() else e

def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def main() -> int:
    if not FULL.exists():
        print("  ★ full_bodies.json が無い: 抽出を見送り (薄いプレビューで作らない)")
        return 1
    bodies = json.loads(FULL.read_text(encoding="utf-8"))
    per: dict = {}
    seen: set = set()
    n_art = 0
    n_hit_art = 0
    rejected = collections.Counter()
    for key, v in bodies.items():
        if not isinstance(v, dict):
            continue
        n_art += 1
        text = re.sub(r"<[^>]+>", " ", str(v.get("text") or ""))
        text = html.unescape(text)
        hits = [s.strip() for s in SPLIT.split(text) if s.strip() and TRIG.search(s)]
        if not hits:
            continue
        n_hit_art += 1
        comp = (v.get("company") or "不明").strip() or "不明"
        for s in hits:
            s = re.sub(r"\s+", " ", s).strip()
            if len(s) < 12:
                continue
            if len(s.split()) > CELLS_MAX:
                rejected["toc_blob"] += 1
                continue
            if not ADJ.search(s):
                rejected["no_adj"] += 1
                continue
            ded = (comp, s[:80])
            if ded in seen:
                continue
            seen.add(ded)
            per.setdefault(comp, []).append({
                "quote": s[:240], "url": v.get("url", ""), "price": v.get("price", ""),
                "title": str(v.get("title", ""))[:90], "note_key": key,
            })
    total = sum(len(v) for v in per.values())
    d = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "text_source": "full HTML body (data/full_bodies.json)",
        "method": "本文を文単位に切り、「逆質問」を含む文だけを採用。文は抽出そのまま。",
        "caveat": ("同じ企業でも記事により書きぶりが違う。空欄は本文に無いということであって、"
                   "逆質問が無かったという意味ではない。"),
        "articles_scanned": n_art,
        "articles_with_reverse_q": n_hit_art,
        "companies": len(per),
        "quotes": total,
        "rejected": dict(rejected),
        "accept_rule": ("逆質問 を含む文から、空白区切り "
                    f"{CELLS_MAX} cell 超の目次塊と、逆質問の直後に述語が無い文を棄却"),
        "per_company": per,
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "reverse_questions.json").write_text(json.dumps(d, ensure_ascii=False, indent=1),
                                                 encoding="utf-8")

    # --- CSV ---
    EXP.mkdir(exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["company", "reverse_question_sentence", "source_url", "source_price_yen",
                "article_title"])
    for c in sorted(per):
        for it in per[c]:
            w.writerow([c, it["quote"], it["url"], it["price"], it["title"]])
            total += 0
    (EXP / "reverse_questions.csv").write_text(buf.getvalue(), encoding="utf_8_sig")
    n_rows = buf.getvalue().count("\n") - 1

    # --- 頁 ---
    pct = round(n_hit_art * 100 / n_art) if n_art else 0
    tops = sorted(per.items(), key=lambda kv: -len(kv[1]))[:24]
    lis = "\n".join(
        f"<li>{comp_link(c)} — {len(v)} 文"
        f"<details><summary>{esc(v[0]['quote'][:96])}</summary>"
        f"<p>{esc(v[0]['quote'])} <a href=\"{esc(v[0]['url'])}\">出典</a></p></details></li>"
        for c, v in tops) or "<li>まだ抽出がありません</li>"
    faq = [
        {"@type": "Question",
         "name": "面接の逆質問は実際に何が聞かれているのか",
         "acceptedAnswer": {"@type": "Answer",
                            "text": (f"収録 {n_art} 本のうち {n_hit_art} 本 ({pct}%) に逆質問への言及が"
                                     f"あり、そこから {total} 文を実文として抽出した。書き手の語に"
                                     "寄せず、本文そのままの1文を載せている。")}},
        {"@type": "Question",
         "name": "逆質問が無い記事はどう扱ったか",
         "acceptedAnswer": {"@type": "Answer",
                            "text": ("空欄は『本文に書かれていない』という意味で、逆質問が無かった意味"
                                     "ではない。推測で文を補っていない。")}},
    ]
    ld = json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "逆質問の実文 (中途面接の記録から抽出)",
        "description": (f"{n_art} 本の面接記録の本文から、逆質問にふれる {total} 文を"
                        f"{len(per)} 社ぶん抽出。出典URLつき。"),
        "url": f"{BASE}/reverse-questions.html",
        "temporalCoverage": "2026-06-04/2026-10-11",
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "application/json",
             "contentUrl": f"{BASE}/data/reverse_questions.json"},
            {"@type": "DataDownload", "encodingFormat": "text/csv",
             "contentUrl": f"{BASE}/exports/reverse_questions.csv"},
        ],
        "creditText": ("記事本文の著作権は note の各記事の著者に帰属。ここにあるのは抽出した対応づけと"
                       "1文の引用です。"),
        "isBasedOn": "https://note.com/shushoku_career1",
        "mainEntityOfPage": {"@type": "WebPage", "@id": f"{BASE}/reverse-questions.html"},
    }, ensure_ascii=False, indent=1)
    ld_faq = json.dumps({"@context": "https://schema.org", "@type": "FAQPage",
                         "mainEntity": faq}, ensure_ascii=False, indent=1)

    doc = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>逆質問の実文 {total} 文 / {len(per)} 社 — 面接記録の抽出 | 目録</title>
<meta name="description" content="収録 {n_art} 本の面接記録のうち {n_hit_art} 本 ({pct}%) に逆質問への言及があった。その実文を {len(per)} 社ぶん出典URLつきで抽出。">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{BASE}/reverse-questions.html">
<script type="application/ld+json">
{ld}
</script>
<script type="application/ld+json">
{ld_faq}
</script>
{tracker("reverse")}
<style>
body{{font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif;margin:0;background:#f6f5f2;color:#1d1c1a;line-height:1.65}}
main{{max-width:900px;margin:0 auto;padding:30px 16px 70px}}
h1{{font-size:1.3rem;margin:0 0 6px}} .sub{{color:#6d675e;font-size:.87rem;margin:0 0 14px}}
.big{{display:flex;gap:18px;flex-wrap:wrap;background:#fff;border:1px solid #e6e1d8;border-radius:9px;padding:13px 15px;margin:14px 0}}
.big div{{font-size:.85rem;color:#4c463e}} .big b{{display:block;font-size:1.3rem;color:#1d1c1a}}
ul{{padding-left:20px;font-size:.87rem}} li{{margin:6px 0}}
details{{margin:3px 0;font-size:.83rem;color:#4c463e}} summary{{cursor:pointer;color:#6d675e}}
.cta{{background:#fff;border:1px solid #e0d8ca;border-radius:9px;padding:12px 15px;font-size:.87rem;margin:16px 0}}
.note{{font-size:.8rem;color:#6d675e;margin-top:22px}} a{{color:#7a5230}}
</style></head><main>
<h1>逆質問の実文 {total} 文 ／ {len(per)} 社</h1>
<p class="sub">面接記録の本文から、逆質問にふれる文だけを選んで出す順番に並べました。文は抽出そのままです。</p>

<div class="big">
  <div><b>{n_hit_art} / {n_art}</b>逆質問に触れる記事 ({pct}%)</div>
  <div><b>{total}</b>抽出した文</div>
  <div><b>{len(per)}</b>カバー企業</div>
</div>

<div class="cta">この抽出も CSV で降ります: <a href="exports/reverse_questions.csv">reverse_questions.csv</a>
（UTF-8 BOM 付き／列は <code>company, reverse_question_sentence, source_url, source_price_yen, article_title</code>）
　企業の絞り込み注文は <a href="data-license.html">データ資産の購入</a>、形の見本は <a href="sample.html">納品物見本</a>。</div>

<h2 style="font-size:1rem">文の数が多い企業 (24社)</h2>
<ul>
{lis}
</ul>

<p class="note">更新: {time.strftime('%Y-%m-%d %H:%M JST')}（毎日 06:10 / 19:40 に自動再生成）
　出典: <a href="https://note.com/shushoku_career1">note / 転職ナビ・中途キャリアの研究所</a>
　権利: 記事本文の著作権は各記事の著者に帰属。公開するのは抽出した対応づけと1文の引用まで。
　<a href="./">目録へ</a> ／ <a href="interview-questions.html">面接質問</a> ／ <a href="selection-signals.html">選考段階</a></p>
</main></body></html>"""
    OUT.write_text(doc, encoding="utf-8")
    print(f"  wrote reverse-questions.html ({len(doc):,} chars) + exports/reverse_questions.csv ({n_rows} 行)")
    print(f"  記事 {n_art} 本中 {n_hit_art} 本 ({pct}%) / 文 {total} / 企業 {len(per)}")
    assert total > 0, "逆質問の抽出が0"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
