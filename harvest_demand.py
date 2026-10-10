#!/usr/bin/env python3
"""検索需要 harvest: Google autocomplete (keyless) から企業別の実際の検索語を取ってくる.

なぜこれが堀か:
  - autocomplete は検索行動の実測であり,後から遡って取得できない
  - 毎日取れば「どの企業にどの疑問が立ち上がったか」の時系列が積める
  - diagnosis: 記事は「100問と回答例」を書いているが, 人要件は 通過率/倍率/回数/圧迫
    → ギャップを数値で示せる

rate limit 事故に備え 0.8s delay + 非200 は 2 回リトライ後にスキップ。
"""
import json
import os
import time
import urllib.parse
import urllib.request
import collections

ROOT = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(ROOT, "data", "corpus_full.json")
OUT = os.path.join(ROOT, "data", "demand_raw.json")
ENDPOINT = "https://www.google.com/complete/search"
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja",
}

# 企業名を cleaning して search 語を作る
import re


def clean_company(c: str) -> str:
    c = re.sub(r"[（(].*?[）)]", "", c)
    c = c.replace("株式会社", "").replace("（現", "").strip(" ・、-")
    return c.strip()


def suggest(q: str, tries=2):
    params = urllib.parse.urlencode({"client": "firefox", "hl": "ja", "gl": "jp", "q": q})
    for i in range(tries):
        try:
            req = urllib.request.Request(f"{ENDPOINT}?{params}", headers=UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status != 200:
                    time.sleep(4)
                    continue
                d = json.load(r)
                return d[1] if len(d) > 1 else []
        except Exception:  # noqa: BLE001
            time.sleep(4)
    return None


def main():
    corpus = json.load(open(CORPUS, encoding="utf-8"))
    companies = {}
    for n in corpus:
        t = n.get("name") or ""
        m = (
            re.match(r"【中途・転職】グッと内定が近づく！(.+?)\s*(?:〈|最終面接|想定)", t)
            or re.match(r"^(.+?)の中途面接対策", t)
            or re.match(r"^(.+?)\s*(?:障害者|障がい者)採用", t)
            or re.match(r"^(.+?)のES", t)
        )
        if not m:
            continue
        c = clean_company(m.group(1))
        if 1 < len(c) <= 20:
            companies.setdefault(c, []).append(n.get("key"))

    names = sorted(companies)
    print(f"companies to probe: {len(names)}", flush=True)

    out = {}
    theme_counter = collections.Counter()
    fail = 0
    for i, c in enumerate(names, 1):
        s = suggest(f"{c} 面接")
        if s is None:
            fail += 1
            continue
        variants = [x for x in s if x != f"{c} 面接"]
        out[c] = {"query": f"{c} 面接", "variants": variants, "count": len(variants)}
        for v in variants:
            tail = v.replace(c, "").replace("面接", "").strip()
            if tail:
                theme_counter[tail] += 1
        if i % 40 == 0:
            print(f"  {i}/{len(names)} probed, {fail} failed", flush=True)
        time.sleep(0.8)

    data = {
        "harvested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": "google.com/complete/search (keyless autocomplete, hl=ja gl=jp)",
        "companies_probed": len(names),
        "companies_failed": fail,
        "companies_with_demand": sum(1 for v in out.values() if v["count"] > 0),
        "question_themes": theme_counter.most_common(60),
        "per_company": out,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    print(f"\nDONE probed={len(names)} failed={fail}", flush=True)
    print(f"  需要シグナルあり: {data['companies_with_demand']} / {len(names)}"
          f" ({data['companies_with_demand']/max(len(names),1)*100:.0f}%)", flush=True)
    print("  top question themes:", flush=True)
    for t, n in theme_counter.most_common(18):
        print(f"    {n:>3}x  {t}", flush=True)


if __name__ == "__main__":
    main()
