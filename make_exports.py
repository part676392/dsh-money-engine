#!/usr/bin/env python3
"""公開している抽出物を CSV に落とす.

 動機: データセットの掲載申請先 (awesome-japanese-nlp-resources など) の読者は
 JSON より CSV を欲しがる。買い手も同じ。なのに repo に CSV が 1つも無かった
 (2026-10-11 実測: 0 個)。

 Excel で開いたときに日本語が文字化けしないよう **UTF-8 BOM 付き**で書く。
 列名は英語 (機械が読む側が主)。中身の文は日本語のまま。
"""
from __future__ import annotations

import csv
import io
import json
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parent
EXP = ROOT / "exports"
SRC = {
    "questions": ROOT / "data" / "interview_questions.json",
    "flows": ROOT / "data" / "selection_flows.json",
    "signals": ROOT / "data" / "selection_signals.json",
}


def load(p: pathlib.Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def write_csv(path: pathlib.Path, header: list, rows: list) -> int:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    path.write_text(buf.getvalue(), encoding="utf_8_sig")  # BOM: Excel で日本語が化けない
    return len(rows)


def main() -> int:
    EXP.mkdir(exist_ok=True)
    q = load(SRC["questions"])
    fl = load(SRC["flows"])
    sg = load(SRC["signals"])
    manifest = []

    # 1) 面接質問
    rows = []
    for comp, items in (q.get("per_company") or {}).items():
        for it in items:
            rows.append([comp, it.get("question", ""), it.get("intent", ""),
                         it.get("article_title", ""), it.get("url", ""),
                         it.get("price", 0), it.get("chars_of_source_text", 0)])
    # 別の builder が書く CSV も manifest には載せる (行数だけ数える)。
    for extra, what in (("question_lineups.csv", "質問カテゴリの並び順 (企業・位置・カテゴリ)"),
                        ("reverse_questions.csv", "逆質問にふれる本文の実文 (出典URLつき)"),
                        ("history_timeseries.csv", "無人巡回が積んだ観測の履歴行列表 (SHA-256 付)")):
        fp = EXP / extra
        if fp.exists():
            with open(fp, encoding="utf_8_sig", newline="") as f:
                manifest.append([extra, max(sum(1 for _ in f) - 1, 0), what])

    n = write_csv(EXP / "interview_questions.csv",
                  ["company", "question", "interviewer_intent", "article_title",
                   "source_url", "article_price_yen", "source_text_chars"], rows)
    manifest.append(["interview_questions.csv", n,
                     "面接で投げられた質問の実文。interviewer_intent は記事が書いた范围のみ"])

    # 2) 選考フロー (1行=1工程 so that it is pivot-able)
    rows = []
    for comp, items in (fl.get("per_company") or {}).items():
        for it in items:
            for i, st in enumerate(it.get("steps", [])):
                rows.append([comp, it.get("track", ""), i + 1, st.get("canon", ""),
                             st.get("raw", ""), it.get("raw", ""), it.get("url", ""),
                             it.get("price", 0)])
    n = write_csv(EXP / "selection_flows.csv",
                  ["company", "track", "step_index", "step_category", "step_as_written",
                   "flow_as_written", "source_url", "article_price_yen"], rows)
    manifest.append(["selection_flows.csv", n,
                     "公式選考フローを1行1工程に割った物。step_as_written が本来の表記"])

    # 3) 選考段階の言及
    # per_company[企業][段階] = {count, quotes[], articles[]} の形。
    # quotes と articles は 1:1 対応じゃないので、出典を勝手に1件に絞らない。
    # article_urls に全URLをスペース区切りで入れる (誠実に、推測で結ばない)。
    rows = []
    for comp, stages in (sg.get("per_company") or {}).items():
        for stage, obj in stages.items():
            urls = " ".join(a.get("url", "") for a in (obj.get("articles") or []))
            prices = "/".join(str(a.get("price", "")) for a in (obj.get("articles") or []))
            for quote in (obj.get("quotes") or []):
                rows.append([comp, stage, obj.get("count", 0), quote, urls, prices])
    n = write_csv(EXP / "selection_signals.csv",
                  ["company", "stage", "mentions_in_source", "quote", "article_urls",
                   "article_prices_yen"], rows)
    manifest.append(["selection_signals.csv", n,
                     "収録記事に現れた選考段階の言及。quote は1文のみ"])

    # 4) 一覧
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    write_csv(EXP / "manifest.csv",
              ["file", "rows", "content"],
              manifest + [["license_scope", "", "CC BY 4.0 はこの表・順序・対応づけにのみ適用。"
                           "本文の著作権は note の各記事の著者に帰属 (source_url を参照)"],
                          ["generated_at", "", stamp],
                          ["encoding", "", "UTF-8 with BOM (utf-8-sig)"]])

    total = sum(m[1] for m in manifest)
    print(f"  wrote 3 CSV + manifest  行数合計={total:,}")
    for m in manifest:
        f = EXP / m[0]
        print(f"    {m[0]:26s} rows={m[1]:5,}  bytes={f.stat().st_size:,}")
    # 先頭行を読み返して実際の中身を検証する (csv reader)
    with open(EXP / "interview_questions.csv", encoding="utf_8_sig", newline="") as f:
        rd = csv.reader(f)
        head = next(rd)
        first = next(rd, None)
    print(f"    読み返し header={len(head)}列  1行目 company={first[0][:16] if first else '—'} "
          f"q={len(first[1]) if first else 0}字")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
