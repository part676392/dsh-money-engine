#!/usr/bin/env python3
"""AI 面接の裏取り文書を、需要のある企業群から機械に探す.

 前回の走査は「ちゃんと見えるドメイン (.co.jp 等)」で通したら 37 件出た。
 中身は AGC の商品サイトとキッコーマンの商品情報で、AI 面接と無関係だった。
 ドメインが正しいだけでは証拠にならない (Bing 総数を索引と誤読した過ちと同型)。
 なのでここでは **タイトルに「面接」かつ AI/録画/動画/面接官** を要求する。
 満たすものが 0 件なら 0 件と書く。それがこの頁の約束。
"""
from __future__ import annotations

import html as H
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
DEMAND = ROOT / "data" / "ai_interview_demand.json"
OUT = ROOT / "data" / "ai_source_scan.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126 Safari/537.36",
      "Accept-Language": "ja"}

TITLE_RE = re.compile(r"面接")
MODE_RE = re.compile(r"AI|ai|録画|動画|面接官")


def serp(q: str) -> str:
    u = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": q, "setlang": "ja", "count": 10})
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def strip(tag: str) -> str:
    return H.unescape(re.sub(r"<[^>]+>", "", tag)).strip()


def scan_company(comp: str) -> dict:
    q = f"{comp} AI面接官 導入"
    try:
        h = serp(q)
    except Exception as e:  # noqa: BLE001
        return {"company": comp, "query": q, "error": str(e)[:80], "hits": []}
    titles = [strip(t) for t in re.findall(r"<h2[^>]*>(.*?)</h2>", h, re.S)]
    cites = [strip(c) for c in re.findall(r"<cite>(.*?)</cite>", h, re.S)]
    hits = []
    for t, c in zip(titles, cites):
        if TITLE_RE.search(t) and MODE_RE.search(t):
            hits.append({"title": t[:140], "cite": c[:160]})
    return {"company": comp, "query": q, "results": len(cites), "hits": hits}


def main() -> int:
    if not DEMAND.exists():
        print("  data/ai_interview_demand.json が無い")
        return 1
    dem = json.loads(DEMAND.read_text(encoding="utf-8"))
    rows = []
    with_hits = 0
    for comp in sorted(dem):
        r = scan_company(comp)
        rows.append(r)
        n = len(r.get("hits") or [])
        if n:
            with_hits += 1
        flag = "★" if n else ("!" if r.get("error") else " ")
        print(f"  {flag} {comp:18s} results={r.get('results', '-'):>2} hits={n}")
        for x in (r.get("hits") or [])[:2]:
            print(f"      · {x['title'][:66]}")
        time.sleep(2.5)
    doc = {
        "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "companies": len(rows),
        "companies_with_hits": with_hits,
        "rule": "title must contain 面接 and one of AI/録画/動画/面接官",
        "rows": rows,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  wrote data/ai_source_scan.json  companies={len(rows)} "
          f"with_hits={with_hits} (raw domain-only hits would have been 37)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
