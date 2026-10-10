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


def fetch(query: str) -> str:
    q = urllib.parse.urlencode({"q": query, "setlang": "ja"})
    req = urllib.request.Request(f"https://www.bing.com/search?{q}", headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def parse(h: str) -> dict:
    """Organic URLs come from <cite>. Bing hides the real target in an
    encrypted /ck/a?p= param, so href scraping returns only bing assets —
    that bug made every earlier reading read 0."""
    import html as _html

    cites = [
        _html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
        for c in re.findall(r"<cite[^>]*>(.*?)</cite>", h, re.S)
    ]
    urls = []
    for c in cites:
        c = c.split("›")[0].strip()
        if c.startswith("http"):
            urls.append(c)
    doms = []
    for u in urls:
        d = re.sub(r"^https?://(www\.)?", "", u).split("/")[0]
        doms.append(d)
    return {
        "http_ok": True,
        "organic_count": len(urls),
        "domains": doms,
        "our_hits": [u for u in urls if SITE in u],
        "our_links_on_page": sum(1 for d in doms if SITE in d),
        # parser self-check: if these are empty, the reading is meaningless.
        "parser_alive": bool(urls),
        "reported_total": (
            (re.search(r"about ([\d,]+) results", h) or re.search(r"([\d,]+) 件の結果", h) or [None, None])[1]
        ),
        "blocked": bool(re.search(r"CAPTCHA|unusual traffic", h)),
    }


def bing(query: str) -> dict:
    try:
        return parse(fetch(query))
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


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
    alive = all(v.get("parser_alive") for v in res["queries"].values() if "error" not in v)
    print(f"TOTAL our-links visible on Bing: {total}", flush=True)
    print(f"parser self-check (must be True): {alive}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
