#!/usr/bin/env python3
"""AI クローラ向けの llms.txt / llms-full.txt に、値段と権利が『生きて』出ているか測る.

AEO の狙いは AI に引用される事。ところが実測 (2026-10-11): llms.txt の中に
料金語・『想定質問』・CC BY が 1 個も無かった (grep 0 件)。
AI が『無料で使える実録の面接質問集』として 引用すると、こちらの注記が届かないまま
誤解が一人歩きする。なので生きている URL の中身を毎回読む。
"""
from __future__ import annotations

import csv
import re
import subprocess
import sys

ROOT = __import__("pathlib").Path(__file__).resolve().parent
BASE = "https://part676392.github.io/dsh-money-engine"
FILES = ["llms.txt", "llms-full.txt"]
NEED = {
    "料金の $5": "$5",
    "料金の $25": "$25",
    "『想定質問』の注記": "想定質問",
    "CC BY 4.0": "CC BY 4.0",
    "受信箱": "fq23ou7os@maxxspace.com",
    "Version 付き zip": "releases/latest",
    "出典": "note.com/shushoku_career1",
}


def fetch(name: str) -> str:
    r = subprocess.run(["curl", "-s", "--max-time", "30", f"{BASE}/{name}"],
                       capture_output=True, text=True)
    return r.stdout


def manifest_rows() -> dict:
    """manifest は配られている物と比べる。実測 (21:0x): ローカル manifest は 720 行、
    live の llms.txt は 735 行で ★ になった — dev と runner が別々に歴史を積むので
    別ツリーの数とぶつかる。同じ場所 (live) 同士で比べる。"""
    out = {}
    raw = fetch("exports/manifest.csv")
    if len(raw) < 40:
        raw = (ROOT / "exports" / "manifest.csv").read_text(encoding="utf_8-sig", errors="replace")
    for r in csv.DictReader(raw.splitlines()):
        if r.get("file"):
            out[r["file"]] = r.get("rows", "")
    return out


def check() -> bool:
    rows = manifest_rows()
    bad = []
    for name in FILES:
        t = fetch(name)
        if len(t) < 400:
            bad.append(f"{name}: 中身が短い ({len(t)} 字 / 配れていない?)")
            continue
        lack = [k for k, w in NEED.items() if w not in t]
        if lack:
            bad.append(f"{name}: 要害の語が無い {lack}")
        # 行数を実数で出している節は manifest と一致している事 (古くなったら嘘になる)
        for m in re.finditer(r"`?([a-z_]+\.csv)`?\s+(\d[\d,]*) 行", t):
            f, n = m.group(1), int(m.group(2).replace(",", ""))
            want = rows.get(f)
            if want is not None and str(want).isdigit() and int(want) != n:
                bad.append(f"{name}: {f} {n:,} 行 / manifest {int(want):,} 行")
        if not bad:
            print(f"    ✓ {name}: 料金・権利・注記 すべて有る ({len(t):,} 字)")
    if bad:
        print("  llms の権利表記  : ★ " + " / ".join(bad[:3]))
        return False
    print(f"  llms の権利表記  : OK ({len(FILES)} file が料金・『想定質問』・CC BY を生出し)")
    return True


if __name__ == "__main__":
    ok = check()
    if not ok:
        print("★★★ GUARD FAIL: llms-rights — AI が読む索引から値段か権利が消えている")
    sys.exit(0 if ok else 1)
