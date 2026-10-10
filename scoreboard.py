#!/usr/bin/env python3
"""Scoreboard: login 無しで測れる指標だけを集めて history に積む.

 判定基準を先に固定した（後から目盛りを動かさない）:
   1. 売上 (note 側) … login 必要なので、取れた日だけ手で記録する
   2. Bing indexation 数 … login 不要・自動計測可 ← このスクリプトが毎回数える
   3. 参考: PV は Bing Webmaster が必要なので使わない

 约定: 売上が出るまで、成果の主張は indexation 数の増減に限る。
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
HIST = ROOT / "data" / "scoreboard"
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
SITE = "part676392.github.io/dsh-money-engine"


def bing(query: str) -> dict:
    q = urllib.parse.urlencode({"q": query, "setlang": "ja"})
    req = urllib.request.Request(f"https://www.bing.com/search?{q}", headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            h = r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
    ours = re.findall(r'href="(https://%s[^"]*)"' % re.escape(SITE), h)
    m = re.search(r"about ([\d,]+) results", h) or re.search(r"([\d,]+) 件の結果", h)
    return {
        "http_ok": True,
        "our_links_on_page": len(set(ours)),
        "sample": sorted(set(ours))[:3],
        "reported_total": m.group(1) if m else None,
        "blocked": bool(re.search(r"CAPTCHA|unusual traffic", h)),
    }


def main() -> int:
    HIST.mkdir(parents=True, exist_ok=True)
    queries = {
        "site_query": f"site:{SITE}",
        "brand": "選考対策 目録データベース",
        "longtail": "中途面接対策 企業別 目録",
    }
    res = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "site": SITE, "queries": {}}
    for name, q in queries.items():
        res["queries"][name] = bing(q)
        res["queries"][name]["query"] = q
        print(f"  {name:10s} {res['queries'][name]}", flush=True)
        time.sleep(2)

    f = HIST / f"{time.strftime('%Y-%m-%d-%H%M')}.json"
    f.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (HIST / "latest.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nsaved {f}", flush=True)
    total = sum(v.get("our_links_on_page", 0) for v in res["queries"].values())
    print(f"TOTAL our-links visible on Bing: {total}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
