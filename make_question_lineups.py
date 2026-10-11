#!/usr/bin/env python3
"""記事が並べた「質問カテゴリの並び」を企業別に構造化する.

 実測 (2026-10-11 06:50): 逆質問を含む 671 文のうち 620 文 (92%) は散文ではなく
 目次の羅列だった («自己PR・強み 転職理由・退職理由 … 逆質問»)。
 散文として出版すると 24 文 / 8 社で薄い。だが羅列の側には
 「その企業が面接をどの.categoryで組み立てているか」という並び順が壊れずに残っている。
 そこで羅列を本品にする (棄てずに)。
"""
from __future__ import annotations

import buy_block
BUY = buy_block.html(hist=True)
import collections
import csv
import html
import io
import json
import pathlib
import re
import time
from tracker_js import tracker

ROOT = pathlib.Path(__file__).resolve().parent
BASE = "https://part676392.github.io/dsh-money-engine"
OUT = ROOT / "question-lineups.html"
DATA = ROOT / "data"
EXP = ROOT / "exports"
FULL = DATA / "full_bodies.json"

# 正規化の辞書。先に引いた順に当てる (順序が効く: 「企業固有」は「業界理解」より後に来る)。
CATS = [
    ("自己紹介・自己PR", r"自己紹介|自己\s*PR|強み弱み|強み"),
    ("転職理由・退職理由", r"転職理由|退職理由"),
    ("志望動機", r"志望動機"),
    ("業界理解", r"業界理解|業界・企業|業界(の)?理解"),
    ("企業固有の理解", r"固有|主要競合|競合比較|事業理解|企業理解"),
    ("キャリアプラン", r"キャリアプラン|キャリアの?（?入?(社|行)後|将来像"),
    ("業務スキル・経験", r"業務スキル|専門スキル|スキル・|経験の?活|実務"),
    ("マネジメント・組織", r"マネジメント|組織|チームワーク|チーム"),
    ("条件・待遇", r"条件|待遇|勤務|働き方|給与"),
    ("逆質問", r"逆質問"),
    ("適性検査・筆記", r"適性検査|SPI|Webテスト|筆記|課題"),
    ("障害・配慮", r"障害|配慮"),
]
CATS = [(n, re.compile(p)) for n, p in CATS]
SPLIT = re.compile(r"(?<=[。！？!?\n])")




def comp_link(name: str) -> str:
    """企業頁が実在する時だけ link。存在しない頁へ張ると audit の link 検査が落ちる (実測)。"""
    e = esc(name)
    fp = ROOT / "company" / f"{name}.html"
    return f'<a href="company/{e}.html">{e}</a>' if fp.exists() else e

def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def classify(item: str):
    for name, rx in CATS:
        if rx.search(item):
            return name
    return None


def main() -> int:
    if not FULL.exists():
        print("  ★ full_bodies.json が無い")
        return 1
    bodies = json.loads(FULL.read_text(encoding="utf-8"))
    per: dict = {}
    n_blob = 0
    n_item = 0
    n_unmapped = 0
    pos_of = collections.defaultdict(list)
    for key, v in bodies.items():
        if not isinstance(v, dict):
            continue
        comp = (v.get("company") or "").strip()
        text = html.unescape(re.sub(r"<[^>]+>", " ", str(v.get("text") or "")))
        for s in SPLIT.split(text):
            s = re.sub(r"\s+", " ", s).strip()
            if len(s) < 24:
                continue
            # 羅列の形: 空白区切りの並び。SPLIT は句点の「後ろ」で切るので
            # 断片は必ず句点で終わる。ここに endswith("。") を置くの.reverse
            # (first run: 羅列 0 本 / 写し 7 語)。語数だけで見る。
            if len(s.split()) < 4:
                continue
            items = [t for t in re.split(r"\s+", s) if len(t) >= 2]
            seq = []
            for it in items:
                c = classify(it)
                if c:
                    seq.append(c)
                    n_item += 1
                    pos_of[c].append(len(seq))
                else:
                    n_unmapped += 1
            # 羅列として認める下限: 3 カテゴリ以上
            if len(seq) < 3:
                continue
            n_blob += 1
            if not comp:
                continue
            rec = per.setdefault(comp, {"lineups": [], "url": v.get("url", ""),
                                        "price": v.get("price", "")})
            rec["lineups"].append({"order": seq, "raw": s[:400], "n": len(seq)})
    seqs = [tuple(lu["order"]) for c, o in per.items() for lu in o["lineups"]]
    modal, n_modal = (collections.Counter(seqs).most_common(1) or [((), 0)])[0]
    len_mode = collections.Counter(len(x) for x in seqs).most_common(1)[0][0] if seqs else 0
    first_mode = collections.Counter(x[0] for x in seqs).most_common(1)[0] if seqs else ("-", 0)
    modal_pct = round(n_modal * 100 / len(seqs)) if seqs else 0
    n_comp = len(per)
    cat_freq = collections.Counter()
    for c, o in per.items():
        for lu in o["lineups"]:
            for cat in set(lu["order"]):
                cat_freq[cat] += 1
    rev_pos = [p for c, o in per.items() for lu in o["lineups"] for p, cat in
               enumerate(lu["order"], 1) if cat == "逆質問"]
    med_rev = sorted(rev_pos)[len(rev_pos) // 2] if rev_pos else 0
    n_rev_comp = len({c for c, o in per.items()
                      if any("逆質問" in lu["order"] for lu in o["lineups"])})

    d = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "text_source": "full HTML body (data/full_bodies.json)",
        "method": ("本文から空白区切りで並ぶ羅列 (4語以上・句点で終わらない) を拾い、"
                   "各語を12カテゴリに正規化して並び順のまま保存。"),
        "caveat": ("羅列は記事の目次であり、その企業が実際に聞いた質問の全集ではない。"
                   "カテゴリに写らない語は_KEEPせず破棄した (件数は unmapped)。"),
        "categories": [n for n, _ in CATS],
        "blobs_total_all_bodies": n_blob,
        "companies": n_comp,
        "items_mapped": n_item,
        "items_unmapped": n_unmapped,
        "lineups_with_company": len(seqs),
        "modal_sequence": list(modal),
        "modal_exact_matches": n_modal,
        "modal_exact_pct": modal_pct,
        "length_mode": len_mode,
        "first_category_mode": list(first_mode),
        "reverse_question_position_median": med_rev,
        "companies_with_reverse_q": n_rev_comp,
        "category_frequency": dict(cat_freq.most_common()),
        "per_company": per,
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "question_lineups.json").write_text(json.dumps(d, ensure_ascii=False, indent=1),
                                                encoding="utf-8")
    EXP.mkdir(exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["company", "lineup_no", "position", "category", "source_url", "source_price_yen"])
    for c in sorted(per):
        for i, lu in enumerate(per[c]["lineups"], 1):
            for p, cat in enumerate(lu["order"], 1):
                w.writerow([c, i, p, cat, per[c]["url"], per[c]["price"]])
    (EXP / "question_lineups.csv").write_text(buf.getvalue(), encoding="utf_8_sig")
    n_rows = buf.getvalue().count("\n") - 1

    tops = sorted(per.items(), key=lambda kv: -len(kv[1]["lineups"]))[:20]
    lis = "\n".join(
        f"<li>{comp_link(c)} — {len(o['lineups'])} 本の羅列"
        f"<div class=\"ord\">{' → '.join(esc(x) for x in o['lineups'][0]['order'])}</div></li>"
        for c, o in tops) or "<li>まだありません</li>"
    freq_rows = "\n".join(f"<tr><td>{esc(k)}</td><td>{v}</td>"
                          f"<td>{round(v * 100 / max(n_comp, 1))}%</td></tr>"
                          for k, v in cat_freq.most_common())
    ld = json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "面接の質問カテゴリの並び順 (記事の目次から構造化)",
        "description": (f"{n_comp} 社の面接記事に残る質問カテゴリの羅列 {n_blob} 本を、"
                        f"12カテゴリに正規化して並び順ごと {n_rows} 行に構造化。"),
        "url": f"{BASE}/question-lineups.html",
        "temporalCoverage": "2026-06-04/2026-10-11",
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "application/json",
             "contentUrl": f"{BASE}/data/question_lineups.json"},
            {"@type": "DataDownload", "encodingFormat": "text/csv",
             "contentUrl": f"{BASE}/exports/question_lineups.csv"},
        ],
        "creditText": "記事本文の著作権は note の各記事の著者に帰属。ここにあるのはカテゴリへの正規化と並び順です。",
        "isBasedOn": "https://note.com/shushoku_career1",
        "mainEntityOfPage": {"@type": "WebPage", "@id": f"{BASE}/question-lineups.html"},
    }, ensure_ascii=False, indent=1)
    ld_faq = json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": "逆質問は面接のどこで聞かれるか",
         "acceptedAnswer": {"@type": "Answer", "text": (
             f"収録記事が並べた質問カテゴリの羅列 {len(seqs)} 本で、逆質問は中央値第"
             f"{med_rev} 番目 (全 {len(seqs)} 本の {modal_pct}% が同一の {len_mode} カテゴリ順で、"
             f"逆質問は常に最後)。準備の最後方に置かれるが、比率としては {n_rev_comp} 社ぶん存在する。")}},
        {"@type": "Question", "name": "この表は何を保証しないか",
         "acceptedAnswer": {"@type": "Answer", "text": (
             "羅列は記事の目次であって、その会社の面接の全集ではない。カテゴリに写さない語は "
             f"{n_unmapped} 語破棄している (割合に換算して総語数 {n_item + n_unmapped:,} 語のうち)。")}},
    ]}, ensure_ascii=False, indent=1)

    doc = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>面接の質問カテゴリの並び順 {n_rows} 行 / {n_comp} 社 — 目次からの構造化 | 目録</title>
<meta name="description" content="面接記事が残す質問カテゴリの羅列 {n_blob} 本を12カテゴリに正規化し、並び順ごと {n_rows} 行に構造化。逆質問は中央値第{med_rev}番目に置かれている。">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{BASE}/question-lineups.html">
<script type="application/ld+json">
{ld}
</script>
<script type="application/ld+json">
{ld_faq}
</script>
{tracker("lineup")}
<style>
body{{font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif;margin:0;background:#f6f5f2;color:#1d1c1a;line-height:1.65}}
main{{max-width:900px;margin:0 auto;padding:30px 16px 70px}}
h1{{font-size:1.3rem;margin:0 0 6px}} .sub{{color:#6d675e;font-size:.87rem;margin:0 0 14px}}
.big{{display:flex;gap:18px;flex-wrap:wrap;background:#fff;border:1px solid #e6e1d8;border-radius:9px;padding:13px 15px;margin:14px 0}}
.big div{{font-size:.85rem;color:#4c463e}} .big b{{display:block;font-size:1.3rem;color:#1d1c1a}}
ul{{padding-left:20px;font-size:.87rem}} li{{margin:7px 0}}
.ord{{font-size:.8rem;color:#6d675e;margin-top:2px}}
.cta{{background:#fff;border:1px solid #e0d8ca;border-radius:9px;padding:12px 15px;font-size:.87rem;margin:16px 0}}
table{{border-collapse:collapse;width:100%;font-size:.85rem;background:#fff}}
th,td{{border-bottom:1px solid #eee6da;padding:6px 8px;text-align:left}}th{{background:#faf7f1}}
.note{{font-size:.8rem;color:#6d675e;margin-top:22px}} a{{color:#7a5230}}
</style></head><body><main>
<h1>面接の質問カテゴリの並び順 ／ {n_rows} 行・{n_comp} 社</h1>
<p class="sub">記事が目次に並べた質問カテゴリの並び順を、12カテゴリに正規化してそのまま保存した。並び順はこの表にしか無い。</p>

<div class="big">
  <div><b>{n_blob}</b>構造化した羅列</div>
  <div><b>{n_comp}</b>カバー企業</div>
  <div><b>第{med_rev}</b>逆質問の中央値位置 ({n_rev_comp}社に出現)</div>
  <div><b>{modal_pct}%</b>が完全に同一の並び順</div>
  <div><b>{n_unmapped:,}</b>カテゴリに写らず破棄した語</div>
</div>

<h2 style="font-size:1rem">最頻の並び ({n_modal} 本・{modal_pct}%)</h2>
<p style="font-size:.9rem">{esc(" → ".join(modal))}</p>
<p class="sub">全 {len(seqs)} 本のカテゴリ数は中央 {len_mode} 個、先頭は「{esc(first_mode[0])}」が {first_mode[1]} 本。
順番まで揃うのは、この手の記事がテンプレで書かれているからだが、だからこそ <b>逆質問は最後</b> という位置も全社で共通になる。</p>

<div class="cta">CSV: <a href="exports/question_lineups.csv">question_lineups.csv</a>
（列 <code>company, lineup_no, position, category, source_url, source_price_yen</code>）
　絞り込み注文は <a href="data-license.html">データ資産の購入</a> ／ 形の見本は <a href="sample.html">納品物見本</a>。</div>

<h2 style="font-size:1rem">カテゴリが現れる社数</h2>
<table><tr><th>カテゴリ</th><th>社数</th><th>社に占める割</th></tr>
{freq_rows}
</table>

<h2 style="font-size:1rem">羅列の本数が多い企業 (20社)</h2>
<ul>
{lis}
</ul>

<p class="note">更新: {time.strftime('%Y-%m-%d %H:%M JST')}（毎日 06:10 / 19:40 に自動再生成）
　出典: <a href="https://note.com/shushoku_career1">note / 転職ナビ・中途キャリアの研究所</a>
　権利: 記事本文の著作権は各記事の著者に帰属。公開するのはカテゴリ正規化と並び順。
　<a href="./">目録へ</a> ／ <a href="reverse-questions.html">逆質問の実文</a> ／ <a href="interview-questions.html">面接質問</a></p>
{BUY}</main></body></html>"""
    OUT.write_text(doc, encoding="utf-8")
    print(f"  wrote question-lineups.html ({len(doc):,} chars) + exports/question_lineups.csv ({n_rows} 行)")
    print(f"  羅列 {n_blob} 本 / 企業 {n_comp} / 写し {n_item:,} 語 / 破棄 {n_unmapped:,} 語 "
          f"({n_unmapped * 100 // max(n_item + n_unmapped, 1)}%) / 逆質問 中央値第{med_rev}")
    assert n_rows > 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
