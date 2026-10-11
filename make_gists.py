#!/usr/bin/env python3
"""Gist 2 本を data から再生成して更新する (面録 data/traffic_sources.json の gist-* に対応)。

Gist は作って終わりだと締切が凍る (作utes 15 件のまま頁は増える)。
毎巡回で本文を組み直して PUT し、変化が無ければ送らない。

  締切    : gist 871c364b0df3d09e7810fe36d3d0016a  (data/gist_deadlines.json)
  並び順  : gist cdaf690435b566d729893d12a69d9670  (data/gist_lineup.json)
"""
from __future__ import annotations

import csv
import json
import pathlib
import statistics
import subprocess
import sys
import collections

ROOT = pathlib.Path(__file__).resolve().parent
SITE = "https://part676392.github.io/dsh-money-engine"


def gh(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, input=stdin, timeout=90)


def deadlines_md() -> tuple:
    dl = json.loads((ROOT / "data" / "es_deadlines_page.json").read_text(encoding="utf-8"))
    rows = dl.get("open") or []
    firms = sorted({r["firm"] for r in rows})
    src = "gist-deadlines"
    lines = ["# 28卒 ES 締切 (機械抽出・根拠文つき)", "",
             f"更新: {dl.get('generated', '?')} / 開いている **{len(rows)} 件**・{len(firms)}社", "",
             f"生の日付と根拠文を全行持たせています: {SITE}/es-deadlines.html?src={src}",
             f"履歴 (いつ・どの記事から拾ったか): {SITE}/exports/es_deadlines_history.csv?src={src}",
             f"目録の本店: {SITE}/?src={src}", "",
             "| 締切 | 社名 | 根拠 (記事からの抜粋) |", "|---|---|---|"]
    for r in rows[:20]:
        ev = (r.get("evidence") or "").replace("|", "／")[:70]
        lines.append(f"| {r['date']} | {r['firm']} | {ev} |")
    lines += ["", "出典は各記事の URL (CSV の source_url 列)。派生表・順序づけにのみ CC BY 4.0。"]
    return ("\n".join(lines) + "\n"), "es-deadlines.md"


def lineup_md() -> tuple:
    f = ROOT / "exports" / "question_lineups.csv"
    rows = list(csv.DictReader(open(f, encoding="utf_8_sig"))) if f.exists() else []
    comps = {r["company"] for r in rows if r.get("company")}
    cat = collections.Counter(r.get("category", "") for r in rows if r.get("category"))
    pos = collections.defaultdict(list)
    for r in rows:
        c, i = r.get("company"), (r.get("position") or r.get("index"))
        if c and i and "逆質問" in (r.get("category") or ""):
            try:
                pos[c].append(int(i))
            except Exception:
                pass
    med = sorted(statistics.median(v) for v in pos.values() if v)
    src = "gist-lineup"
    lines = ["# 面接質問の並び順 (実測)", "",
             f"質問行 **{len(rows):,}** / 企業 **{len(comps)}** 社。記事の実文を落とした形で、各行に企業の出典 URL。",
             "",
             f"頁: {SITE}/question-lineups.html?src={src}",
             f"CSV: {SITE}/exports/question_lineups.csv?src={src}",
             f"店の頁: {SITE}/store/?src={src}", "",
             "| カテゴリ | 行数 |", "|---|---|"]
    for k, v in cat.most_common(8):
        lines.append(f"| {k} | {v:,} |")
    lines += ["",
              f"逆質問が現れる位置の中央値 (企業別): {med[len(med) // 2] if med else '—'} 番目 / 対象 {len(pos)} 社",
              "",
              "無償で落とせる CSV (UTF-8 BOM 付き)。派生表・順序づけにのみ CC BY 4.0、本文の著作権は note の各記事の著者に帰属。"]
    return ("\n".join(lines) + "\n"), "question-lineups.md"


def push(meta_name: str, builder) -> str:
    meta_p = ROOT / "data" / meta_name
    if not meta_p.exists():
        return f"  ★ {meta_name} が無い (gist を作っていない)"
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    md, fname = builder()
    r = gh("api", f"/gists/{meta['id']}", "--jq", f".files[\"{fname}\"].content")
    # gh の --jq は末尾の改行を落とすので、そこは揃えて比べる (毎回 PATCH して空振りしていた)
    cur = r.stdout.rstrip("\n") if r.returncode == 0 else ""
    if cur == md.rstrip("\n"):
        return f"  {meta_name:20s} 変化なし ({len(md):,}字)"
    payload = json.dumps({"files": {fname: {"content": md}}}, ensure_ascii=False)
    put = gh("api", "-X", "PATCH", f"/gists/{meta['id']}", "--input", "-", stdin=payload)
    if put.returncode != 0:
        return f"  ★ {meta_name} 更新失敗: {put.stderr.strip()[:120]}"
    back = gh("api", f"/gists/{meta['id']}", "--jq", f".files[\"{fname}\"].content").stdout
    ok = back.rstrip("\n") == md.rstrip("\n") and "src=" in back
    return f"  {meta_name:20s} {'更新 OK' if ok else '★ 読み返し不一致'} ({len(md):,}字) {meta['url']}"


def main() -> int:
    out = [push("gist_deadlines.json", deadlines_md), push("gist_lineup.json", lineup_md)]
    for l in out:
        print(l)
    return 1 if any("★" in l for l in out) else 0


if __name__ == "__main__":
    sys.exit(main())
