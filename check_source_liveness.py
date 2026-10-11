#!/usr/bin/env python3
"""出典 (note.com の記事) が生きているか測る。毎巡回で少しずつ全量を回す。

面の約束: 「各 INSERT 行に source_url (出典) を付ける」/ 「出典URLつき」。
出先が 404 になったら約束が嘘になる。実測: これまで生存を一度も測っていなかった
(data/history に liveness の台帳が無く、faces の link を生かしたままだった)。

  台帳 : data/history/source_liveness.jsonl  (1 行 = 1 記事 1 観測)
  記録 : http / bytes / 有料化の目印 /购买了标价 (price)
  危険 : 以前 200 だった物が 200 でなくなった / 無料だった物が有料になった
         → ★ GUARD FAIL: source-liveness (面の約束が嘘になる為)

全 600 本を 1 回で回すと note 側に負荷なので、日と回で決定的に割いて測る
(実測の感覚: 0.35 秒間隔なら 1 巡回 80 本で約 1 分。3 巡回/日なら 2.5 日で全量)。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
CORPUS = ROOT / "data" / "corpus_full.json"
LEDGER = ROOT / "data" / "history" / "source_liveness.jsonl"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")
import os

# 制御 (guard が本当に走るか確かめる注入) と実運用で台帳を分ける為、外から差し替えられる。
PER_RUN = int(os.environ.get("DSH_LIVENESS_PER_RUN", "80"))
SLEEP = float(os.environ.get("DSH_LIVENESS_SLEEP", "0.35"))
BASE = os.environ.get("DSH_NOTE_BASE", "https://note.com/shushoku_career1/n")
if os.environ.get("DSH_LIVENESS_LEDGER"):
    LEDGER = pathlib.Path(os.environ["DSH_LIVENESS_LEDGER"])
PAYWALL = ("このnoteは有料", "購入して続きを読む", "ログインして読む", "members only")


def today() -> dt.date:
    import os
    return dt.date.fromisoformat(os.environ["DSH_AS_OF"]) if os.environ.get("DSH_AS_OF") else dt.date.today()


def sample(keys: list) -> list:
    """日と回で決定的に割く (総当たりで全量を回せるように)。"""
    # 制御用:  Specific key を差し替えられる (回す度に見る記事が変わると、
    # 「前回 200 → 今回 404」の注入を試せない為。実測で control が空振りした)
    force = [k.strip() for k in os.environ.get("DSH_LIVENESS_KEYS", "").split(",") if k.strip()]
    if force:
        want = {k: (k, n, p) for k, n, p in keys}
        return [want[k] for k in force if k in want]
    d = today().isoformat()
    n_prev = ledger_count()
    seed = int(hashlib.sha1((d + str(n_prev)).encode()).hexdigest(), 16)
    return [keys[(seed + i) % len(keys)] for i in range(min(PER_RUN, len(keys)))]


def ledger_count() -> int:
    if not LEDGER.exists():
        return 0
    return sum(1 for _ in LEDGER.open(encoding="utf-8"))


def last_seen() -> dict:
    """記事キーの最終観測 (死んだ判定の基準)。"""
    out: dict = {}
    if not LEDGER.exists():
        return out
    with LEDGER.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            out[r.get("key")] = r
    return out


def fetch(key: str) -> tuple:
    url = f"{BASE}/{key}"
    p = subprocess.run(["curl", "-s", "-o", "-", "-w", "\n@@%{http_code} %{size_download}",
                        "--max-time", "25", "-A", UA, url], capture_output=True, text=True)
    body, _, meta = p.stdout.rpartition("\n@@")
    bits = meta.split()
    code = int(bits[0]) if bits and bits[0].isdigit() else 0
    size = int(bits[1]) if len(bits) > 1 and bits[1].isdigit() else 0
    return code, size, body


def check(quiet: bool = False) -> dict:
    corpus = json.load(open(CORPUS, encoding="utf-8"))
    keys = [(n.get("key"), n.get("name") or "", n.get("price") or 0) for n in corpus if n.get("key")]
    prev = last_seen()
    rows, dead, paywalled = [], [], []
    for key, name, price in sample(keys):
        code, size, body = fetch(key)
        paid = any(m in body for m in PAYWALL)
        r = {"seen": today().isoformat(), "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
             "key": key, "http": code, "bytes": size, "paywall": paid,
             "price": price, "title": name[:60]}
        rows.append(r)
        b = prev.get(key)
        if b and b.get("http") == 200 and code != 200:
            dead.append(f"{key} {code} (前回 200) {name[:24]}")
        if b and not b.get("paywall") and paid:
            paywalled.append(f"{key} 無料→有料 {name[:24]}")
        time.sleep(SLEEP)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    seen_keys = set()
    if LEDGER.exists():
        for line in LEDGER.open(encoding="utf-8"):
            try:
                seen_keys.add(json.loads(line).get("key"))
            except Exception:
                continue
    http0 = [r for r in rows if r["http"] == 0]
    stats = {"observed": len(rows), "ledger": ledger_count(), "covered": len(seen_keys),
             "of": len(keys), "dead": dead, "paywalled": paywalled, "no_http": len(http0)}
    if not quiet:
        print(f"  出典の生存      : 今回 {stats['observed']} 本 / 累計 {stats['covered']}/{len(keys)} 記事"
              f" / 200 以外 {len([r for r in rows if r['http'] != 200])} / 有料化 {len(paywalled)}")
        if dead:
            print(f"    ★ 死んだ出典 {len(dead)}: {dead[:3]}")
        if paywalled:
            print(f"    ★ 有料化 {len(paywalled)}: {paywalled[:3]}")
        if http0:
            print(f"    ★ http が取れない {len(http0)} 本 (測れていない)")
    return stats


CSV_OUT = ROOT / "exports" / "source_liveness.csv"
CSV_COLS = ["seen", "at", "key", "url", "http", "bytes", "paywall", "price", "title"]


def write_csv(quiet: bool = False) -> int:
    """$25 の『歴史スナップショット一式』に入れる成果物としても出す (店に出す物は CSV)。"""
    import csv as _csv
    rows = []
    if LEDGER.exists():
        for line in LEDGER.open(encoding="utf-8"):
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    if not rows:
        return 0
    rows.sort(key=lambda r: (str(r.get("seen")), str(r.get("at")), str(r.get("key"))))
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", encoding="utf_8_sig", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r["url"] = f"{BASE}/{r.get('key')}"
            w.writerow(r)
    if not quiet:
        print(f"  生存 CSV   : {CSV_OUT.name} {len(rows)} 行")
    return len(rows)


if __name__ == "__main__":
    st = check()
    write_csv()
    # 死んだ出典は約束の違反 / http が取れない日は測れていない (0 と区別する)
    if st["dead"] or st["paywalled"] or st["no_http"]:
        print("★★★ GUARD FAIL: source-liveness — 出典の生存が変わったか測れていない")
        sys.exit(1)
    print("  出典の生存 OK")
