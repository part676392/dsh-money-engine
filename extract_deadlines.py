#!/usr/bin/env python3
"""ES 締切を高精度で抽出し直す.

 前段の緩い抽出は note 共通ヘッダ（「メインコンテンツへスキップ … 2026年10月9日」）を
 拾って公開日を締切と誤爆した。ここでは:
   - 本文をフルで取り直す（保存済 evidence の 150字切り出しに依存しない）
   - 「締切」語から12字以内に 2026年M月D日 が居るものだけ
   - note ヘッダ文言を含む一致は除外
 根拠文はそのまま保存して、後から人間が検証できる状態にする。
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
TODAY = dt.date(2026, 10, 10)

STRICT = re.compile(
    r"(?:締切|〆切|提出期限|応募期限|エントリー締切|ES締切|応募締切)\D{0,12}?2026\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
)
BAD = ("メインコンテンツへスキップ", "転職ナビ・中途キャリアの研究所")


def firm_of(t: str) -> str:
    f = re.split(r"のES|ES、|ESは|ES例文|インターンES", t)[0]
    f = re.sub(r"【[^】]*】", "", f)
    return f.strip(" ・")[:24]


def main() -> None:
    corpus = json.load(open(ROOT / "data" / "corpus_full.json", encoding="utf-8"))
    es = [n for n in corpus if "ES" in (n.get("name") or "")]
    print(f"ES articles to re-fetch: {len(es)}")

    rows = []
    for n in es:
        url = f"https://note.com/shushoku_career1/n/{n.get('key')}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
                h = r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            print(f"  fetch fail {n.get('key')}: {e}")
            time.sleep(0.5)
            continue
        txt = re.sub(r"<script.*?</script>", " ", h, flags=re.S)
        txt = re.sub(r"<[^>]+>", " ", txt)
        txt = re.sub(r"\s+", " ", txt)

        for m in STRICT.finditer(txt):
            ev = re.sub(r"\s+", " ", m.group(0)).strip()
            if any(b in ev for b in BAD):
                continue
            mo, da = int(m.group(1)), int(m.group(2))
            try:
                d = dt.date(2026, mo, da)
            except ValueError:
                continue
            t = n.get("name") or ""
            rows.append(
                {
                    "firm": firm_of(t),
                    "date": d.isoformat(),
                    "days": (d - TODAY).days,
                    "price": n.get("price") or 0,
                    "likes": n.get("likeCount") or 0,
                    "url": url,
                    "evidence": ev[:180],
                    "title": t[:74],
                }
            )
        time.sleep(0.45)

    # (firm, date) で重複排除、最も長い根拠文を残す
    seen: dict = {}
    for r in sorted(rows, key=lambda r: -len(r["evidence"])):
        seen.setdefault((r["firm"], r["date"]), r)
    final = sorted(seen.values(), key=lambda r: (r["days"], -r["price"]))
    future = [r for r in final if r["days"] >= 0]

    print(f"\nstrict-confirmed deadlines: {len(final)}  |  締切前: {len(future)}  (旧 2 件)")
    for r in future[:18]:
        tag = "🆓" if not r["price"] else f"¥{r['price']:,}"
        print(f"  {r['date']}  残り{r['days']:>3}日 {tag:>6} {r['firm'][:22]:24s} 「{r['evidence'][:58]}」")

    out = ROOT / "data" / "es_deadlines_strict.json"
    out.write_text(
        json.dumps(
            {"generated": TODAY.isoformat(), "method": "strict-adjacency", "open": future, "all": final},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
