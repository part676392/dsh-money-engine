#!/usr/bin/env python3
"""ES 締切を全 600 記事の本文から根拠付きで洗い直す ( widen / widen+年 ゆるめ )。

前までの物: extract_deadlines.py は「ES」語を含む記事だけを fetch し、窓 12 字、年 2026 だけ。
実測で残ったのは 21 行 (開いている 12 行) だけだった。cache (corpus_full.json の body) は
1 記事 240 字の要約なので締切語が落ちる (実測: 本文 cache では 9 ヒットだけ)。
ここでは全記事を fetch し直し、語を緩め (締切/締め切り/〆切/提出期限/応募期限/受付期限/選考締切)、
窓 40 字、年を 2026 と 2027 を許す。ただし対句 (語と日付が近い) は崩さない = 誤爆は許すが見当違いは出さない。
誤爆の筋 (note の共通ヘッダの公開日) は前段と同じ文言で除外する。
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")}
WORD = (r"(?:ES\s*締切|エントリー締切|応募締切|選考締切|一次締切|提出期限|応募期限|受付期限"
        r"|締切日|締切|締め切り|〆切)")
DATE = r"20(2[67])\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
BAD = ("メインコンテンツへスキップ", "転職ナビ・中途キャリアの研究所")
OUT = ROOT / "data" / "es_deadlines_wide.json"
PROG = ROOT / "data" / "es_deadlines_wide.progress.json"


def clean(t: str) -> str:
    t = re.sub(r"<script.*?</script>", " ", t, flags=re.S)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t)


def firm_of(t: str) -> str:
    f = re.split(r"のES|ES、|ESは|ES例文|インターンES|の選考|選考", t)[0]
    f = re.sub(r"【[^】]*】", "", f)
    return f.strip(" ・")[:24]


def main() -> int:
    today = dt.date.today()
    corpus = json.load(open(ROOT / "data" / "corpus_full.json", encoding="utf-8"))
    pat = re.compile(WORD + r"\D{0,40}?" + DATE)
    rows: list = []
    fetched = fails = 0
    seen: set = set()
    t0 = time.time()
    for i, n in enumerate(corpus, 1):
        key = n.get("key")
        if not key:
            continue
        url = f"https://note.com/shushoku_career1/n/{key}"
        title = n.get("name") or ""
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
                h = r.read().decode("utf-8", "replace")
            fetched += 1
        except Exception as e:                                    # noqa: BLE001
            fails += 1
            print(f"  fetch fail {key}: {type(e).__name__}", flush=True)
            time.sleep(1.2)
            continue
        txt = clean(h)
        for m in pat.finditer(txt):
            ev = m.group(0).strip()
            if any(b in ev for b in BAD):
                continue
            mo, da = int(m.group(2)), int(m.group(3))
            try:
                d = dt.date(int(m.group(1)), mo, da)
            except ValueError:
                continue
            dk = (key, d.isoformat())
            if dk in seen:
                continue
            seen.add(dk)
            rows.append({"firm": firm_of(title), "date": d.isoformat(),
                         "days": (d - today).days, "price": n.get("price") or 0,
                         "likes": n.get("likeCount") or 0, "url": url, "key": key,
                         "evidence": ev[:200], "title": title[:74]})
        if i % 40 == 0:
            print(f"  {i}/{len(corpus)} fetch={fetched} fail={fails} rows={len(rows)}"
                  f"  {(time.time()-t0)/60:.1f} 分", flush=True)
            PROG.write_text(json.dumps({"done": i, "of": len(corpus), "fetched": fetched,
                                        "fails": fails, "rows": len(rows)}, ensure_ascii=False),
                            encoding="utf-8")
        time.sleep(0.35)

    open_rows = [r for r in rows if r["days"] >= 0]
    open_rows.sort(key=lambda r: (r["date"], r["firm"]))
    # 検証: evidence は fetch した本文に実在する語だけ (機械で引き直したので筋は切れない)
    bad = [r for r in rows if not re.search(r"\d{1,2}月\d{1,2}日", r["evidence"])]
    OUT.write_text(json.dumps({"generated": today.isoformat(), "today": today.isoformat(),
                               "method": "wide-adjacency 40字 / 2026+2027 / 全 600 記事 fetch",
                               "fetched": fetched, "fails": fails,
                               "all": rows, "open": open_rows},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  fetch {fetched} / fail {fails} / rows {len(rows)} / 開いている {len(open_rows)}"
          f" / 社 {len({r['firm'] for r in open_rows if r['firm']})} / 日付 {len({r['date'] for r in open_rows})}"
          f" / evidence に日付の無い行 {len(bad)}")
    for r in open_rows[:4]:
        print(f"    {r['date']} (+{r['days']:3d}日) {r['firm'][:16]:16s} {r['evidence'][:56]}")
    return 0 if fetched > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
