#!/usr/bin/env python3
"""自分が開いている PR の本文に、ES 締切の面を 1 行足す (追記は自分の PR だけ)。

開いている PR 3 本は人が click した記録の有る唯一の面 (実測 src-pr32 / src-jopendata)。
そこに締切の面への link が無かったので、季節の需要に対して入口が 1 つ足りない。
本文は消さずに 1 行だけ足し、?src=<面の鍵> を付けてどこから来たか区別する。
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SITE = "https://part676392.github.io/dsh-money-engine"
MARK = "ES deadlines ("
PRS = [
    ("taishi-i/awesome-japanese-nlp-resources", 32, "pr32"),
    ("okhosting/awesome-open-data", 57, "pr57"),
    ("japan-opendata/awesome-japan-opendata", 30, "jopendata"),
]


def gh(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, input=stdin, timeout=90)


def line(key: str, rows: int, firms: int, span: str) -> str:
    return (f"{MARK}open, with the sentence each date was pulled from{CLOSE} "
            f"{rows} entries / {firms} firms / {span}: "
            f"{SITE}/es-deadlines.html?src={key}")


CLOSE = ")"


def main() -> int:
    p = ROOT / "data" / "es_deadlines_page.json"
    rows = (json.loads(p.read_text(encoding="utf-8")).get("open") or []) if p.exists() else []
    firms = len({r.get("firm") for r in rows})
    dates = sorted({r.get("date") for r in rows if r.get("date")})
    span = f"{dates[0]}-{dates[-1]}" if dates else "no dated rows"
    bad = 0
    for repo, num, key in PRS:
        cur = gh("api", f"repos/{repo}/pulls/{num}", "--jq", ".body").stdout
        add = line(key, len(rows), firms, span)
        if MARK in cur:
            print(f"  {repo}#{num}: 既に入っているので変更なし ({len(rows)} 件は面の側で再生成される)")
            continue
        new = cur.rstrip("\n") + "\n\n" + add + "\n"
        payload = json.dumps({"body": new}, ensure_ascii=False)
        r = gh("api", "-X", "PATCH", f"repos/{repo}/pulls/{num}", "--input", "-", stdin=payload)
        if r.returncode != 0:
            print(f"  ★ {repo}#{num}: 更新失敗 {r.stderr.strip()[:120]}")
            bad += 1
            continue
        back = gh("api", f"repos/{repo}/pulls/{num}", "--jq", ".body").stdout
        ok = f"src={key}" in back and "es-deadlines.html" in back
        print(f"  {repo}#{num}: 読み返し {'OK' if ok else '★ 反映されていない'} / 本文 {len(back):,}字 / {add[-42:]}")
        if not ok:
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
