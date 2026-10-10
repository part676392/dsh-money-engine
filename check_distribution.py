#!/usr/bin/env python3
"""配布面が生きているか、リンクが落ちしていないかを無人で確認する.

 今日作って壊れたもの:
   - heredoc を 'EOF' で作らなかったせいで shell が $6 を展開し、
     配布ページの価格が空になった。作業者のシェル事故であって
     掲載先の不具合ではなかった。だからここで毎度 '価格が表示されているか' を見る。
   - Telegraph は access token を要求するようになった (Telegram 認可=人を要る)
   - Lemmy 0.19 は password_verify 必須、さらに captcha_incorrect
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent
HIST = ROOT / "data" / "distribution"
STORE_MARK = "part676392.github.io/dsh-money-engine/store"

SURFACES = [
    {"name": "gist", "url": None, "needs": [STORE_MARK]},
    {"name": "rentry_v2", "url": None, "needs": ["6 USD", STORE_MARK, "18+"]},
    {"name": "rentry_v3", "url": None, "needs": ["730 words", "Dryers on Carver Street",
                                                   "3 USD", "6 USD", "9 USD", STORE_MARK]},
]


def fetch(url: str) -> str:
    try:
        r = subprocess.run(["curl", "-sL", "--max-time", "25", url],
                           capture_output=True, text=True, timeout=30)
        return r.stdout
    except Exception:  # noqa: BLE001
        return ""


def load_urls() -> None:
    g = ROOT / "data" / "gist_url.txt"
    if g.exists():
        for s in SURFACES:
            if s["name"] == "gist":
                s["url"] = g.read_text(encoding="utf-8").strip()
    rj = ROOT / "data" / "rentry.json"
    if rj.exists():
        d = json.loads(rj.read_text(encoding="utf-8"))
        for s in SURFACES:
            if s["name"] == "rentry_v2":
                s["url"] = d.get("v2_url") or d.get("url")
            if s["name"] == "rentry_v3":
                s["url"] = d.get("v3_url")


def main() -> int:
    HIST.mkdir(parents=True, exist_ok=True)
    load_urls()
    out = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "surfaces": {}}
    ok_all = True
    for s in SURFACES:
        if not s["url"]:
            print(f"  {s['name']:10s} SKIP (url 未記録)")
            ok_all = False
            continue
        h = fetch(s["url"])
        present = [n for n in s["needs"] if n in h]
        good = len(present) == len(s["needs"]) and len(h) > 800
        ok_all = ok_all and good
        mark = "✓" if good else "✗"
        missing = [n for n in s["needs"] if n not in present]
        print(f"  {mark} {s['name']:10s} bytes={len(h):6d} ok={good}"
              + (f" missing={missing}" if missing else ""))
        print(f"      {s['url']}")
        out["surfaces"][s["name"]] = {"url": s["url"], "bytes": len(h),
                                      "ok": good, "missing": missing}
    (HIST / "latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    with open(HIST / f"{time.strftime('%Y-%m-%d-%H%M')}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n  all surfaces live: {ok_all}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
