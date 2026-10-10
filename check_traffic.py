#!/usr/bin/env python3
"""自分の访问数を、鍵なしで読戻しまでできる計器で測る.

 前段の実測で死んだ計器:
   Google /ping   -> 404 (endpoint 廃止)
   Bing  /ping    -> 410 Gone
   Bing SERP      -> 最初は使えるが数分で絞られ、daikin を返し始めた
   DuckDuckGo html-> challenge (bot壁) を返す。21 mentions は全部 query のエコーだった
   countapi.xyz   -> DNS 解決不能

 なので索引の"代理"を測るのはやめて、直接測れる访问を測る。
 pixel は img なので JS 不要。Bot も数える。自分の audit も数える。
 それは減算せず、事実として history に残す。
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent
HIST = ROOT / "data" / "traffic"
BASE = "https://abacus.jasoncameron.dev"
KEYS = {"store": "store", "home": "home", "mini": "mini", "license": "license"}
SITE = "https://part676392.github.io/dsh-money-engine"


def api(path: str) -> dict:
    try:
        r = subprocess.run(["curl", "-s", "--max-time", "15", f"{BASE}{path}"],
                           capture_output=True, text=True, timeout=20)
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:70]}


def main() -> int:
    HIST.mkdir(parents=True, exist_ok=True)
    prev_f = HIST / "latest.json"
    prev = json.loads(prev_f.read_text(encoding="utf-8")) if prev_f.exists() else {}

    out = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "counters": {}}
    for label, key in KEYS.items():
        g = api(f"/get/dsh-money-engine/{key}")
        v = g.get("value")
        old = (prev.get("counters", {}).get(label) or {}).get("value")
        delta = (v - old) if (isinstance(v, int) and isinstance(old, int)) else None
        out["counters"][label] = {"value": v, "delta": delta, "key": key}
        arrow = "" if not delta else f"  ↑ +{delta}"
        print(f"  {label:6s} hits={v}{arrow}", flush=True)

    print(f"\n  site: {SITE}/store/  (pixel は実在する img)")
    (HIST / "latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(HIST / f"{time.strftime('%Y-%m-%d-%H%M')}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # pixel が実際にページへ埋まっているか、生の HTML を見て確認する
    try:
        r = subprocess.run(["curl", "-s", "--max-time", "20", f"{SITE}/store/"],
                           capture_output=True, text=True, timeout=25)
        embedded = "abacus.jasoncameron.dev/hit/dsh-money-engine/store" in r.stdout
        print(f"  pixel embedded in live store page: {embedded}")
    except Exception as e:  # noqa: BLE001
        print(f"  pixel check failed: {str(e)[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
