#!/usr/bin/env python3
"""run の開始と終了を git の届かない場所に1行ずつ積む.

 なぜ: 日志 logs/daily_*.log は git 追跡下 (運用履歴の素材なので)。
 だから run の途中で pull/rebase が内容を書き戻すことがあり、
 「今 run が動いたか」の目撃者に使えない。実測: 05:09:13 start の後
 40行以上書いたのに日志の末尾が start のままだった (完了は guards の
 05:11:05 が証明)。目撃者は git の届かない所に置く。
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
LOGS = ROOT / "logs"
FILE = LOGS / "runs.jsonl"   # .gitignore 済み (git に書き戻されない)


def head() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                           text=True, timeout=15)
        return r.stdout.strip() or "?"
    except Exception:
        return "?"


def main() -> int:
    LOGS.mkdir(exist_ok=True)
    phase = sys.argv[1] if len(sys.argv) > 1 else "note"
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "phase": phase,
           "where": "runner" if str(ROOT).startswith("/Users") and "dsh-runner" in str(ROOT) else "dev",
           "root": str(ROOT), "head": head()}
    for a in sys.argv[2:]:
        if "=" in a:
            k, v = a.split("=", 1)
            rec[k] = v
    with open(FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  run log: {phase} ({rec['where']} {rec['head']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
