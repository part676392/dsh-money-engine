#!/usr/bin/env python3
"""note corpus 全文量取得.

前回 360/1,056 (34%) でページ上限により打ち切った。
ページ上限を外し、isLastPage / noteCount に到達するまで取得する。
 rate limit 事故防止に 0.45s の polite delay と 2 回リトライ。
"""
import json
import time
import urllib.request
import urllib.error
import sys

ACCT = "shushoku_career1"
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
OUT = "/Users/moherune/Documents/deepseek-harness/default-workspace/dsh-money-engine/data/corpus_raw.json"


def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code == 403:  # rate limited: back off hard
                time.sleep(20 * (i + 1))
            else:
                time.sleep(3)
        except Exception as e:  # noqa: BLE001
            last = str(e)
            time.sleep(3)
    print(f"    give up: {last}", flush=True)
    return None


prof = get(f"https://note.com/api/v2/creators/{ACCT}")
target = (prof or {}).get("data", {}).get("noteCount", 0)
print(f"target noteCount = {target}", flush=True)

notes = []
seen = set()
page = 1
stale = 0
while page <= 260:
    res = get(f"https://note.com/api/v2/creators/{ACCT}/contents?kind=note&page={page}")
    if not res or "data" not in res:
        print(f"  page {page}: no data, stopping", flush=True)
        break
    cs = res["data"].get("contents") or []
    if not cs:
        print(f"  page {page}: empty, stopping", flush=True)
        break
    before = len(notes)
    for c in cs:
        k = c.get("key")
        if k and k not in seen:
            seen.add(k)
            notes.append(c)
    if len(notes) == before:
        stale += 1
        if stale >= 3:
            print(f"  page {page}: 3 pages with no new keys, stopping", flush=True)
            break
    else:
        stale = 0
    if page % 20 == 0 or res["data"].get("isLastPage"):
        print(f"  page {page}: total {len(notes)}", flush=True)
    if res["data"].get("isLastPage"):
        print("  isLastPage reached", flush=True)
        break
    if target and len(notes) >= target:
        print("  target reached", flush=True)
        break
    page += 1
    time.sleep(0.45)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(notes, f, ensure_ascii=False)

prices = sum(n.get("price") or 0 for n in notes)
free = sum(1 for n in notes if not (n.get("price") or 0))
print(f"\nFETCHED {len(notes)} records -> {OUT}", flush=True)
print(f"  free {free} / paid {len(notes)-free}  listed ¥{prices:,}", flush=True)
