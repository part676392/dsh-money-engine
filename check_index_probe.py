#!/usr/bin/env python3
"""検索エンジンが『今』自分の面を出すかを毎回実測して台帳に積む。

実測 (2026-10-11 14:4x):
  IndexNow 送信        : bing.com/indexnow status 200 (487 本) / key file http=200
                         (host 直下の既定 url は 404 — project page なので keyLocation を
                          /dsh-money-engine/<key>.txt に置いている。ループはそう送っている)
  Bing "site:part676392.github.io" : 結果らしき li 10 個のうち自ドメイン 0 件
  Bing 正確一致 (h1 文面)          : 自ドメイン 0 件
  DuckDuckGo html                 : http=202 (規制で本文が無しのことがある)
だから『索引されたか』は今 測れない が正解。0 を 0 と記録し、測れなかった日を ★ にする。
Google は IndexNow を見ないので Search Console (人の閘門) が要る。
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent
HOST = "part676392.github.io"
SITE = "https://part676392.github.io/dsh-money-engine"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")
LEDGER = ROOT / "data" / "history" / "index_probe.jsonl"
# 代表作 3 面 (HOME は索引されていても当たり前なので見ない)
EXACT = [
    ("deadlines", "28卒 コンサル・ファーム ES 締切一覧"),
    # 文面は面の h1 から写した (実測: 「面接の質問カテゴリの並び順 ／ 5494 行・467 社」
    # / 「逆質問の実文 24 文 ／ 8 社」)。無い文面で 0 件を出しても測ったことにならない。
    ("lineups", "面接の質問カテゴリの並び順"),
    ("reverse", "逆質問の実文"),
]


def curl(url: str, timeout: int = 30) -> tuple:
    p = subprocess.run(["curl", "-s", "-o", "-", "-w", "\n@@%{http_code}",
                        "--max-time", str(timeout), "-A", UA, url],
                       capture_output=True, text=True)
    body, _, code = p.stdout.rpartition("\n@@")
    return (int(code) if code.strip().isdigit() else 0), body


def probe(quiet: bool = False) -> dict:
    row = {"seen": dt.date.today().isoformat(), "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    bad = []
    # site: 検索
    code, body = curl(f"https://www.bing.com/search?q={urllib.parse.quote('site:' + HOST)}&count=30")
    mine = len(set(re.findall(re.escape(HOST) + r"/[a-zA-Z0-9%/_.-]*", body)))
    shell = "b_algo" in body          # 実結果頁か (JS の外枠だけなら 0 を 0 とは言えない)
    row["bing_site_http"] = code
    row["bing_site_mine"] = mine
    row["bing_site_shell"] = shell
    if code not in (200, 201):
        bad.append(f"bing site: http={code}")
    elif not shell:
        bad.append("bing site: 結果頁の外殻 (b_algo) が無い = 0 件と言えない")
    time.sleep(1.0)
    # 面ごとの正確一致
    for key, phrase in EXACT:
        code, body = curl("https://www.bing.com/search?q="
                          + urllib.parse.quote('"' + phrase + '"') + "&count=20")
        urls = set(re.findall(re.escape(HOST) + r"/[a-zA-Z0-9%/_.-]*", body))
        row[f"bing_{key}_http"] = code
        row[f"bing_{key}_mine"] = len(urls)
        row[f"bing_{key}_urls"] = sorted(urls)[:3]
        if code not in (200, 201):
            bad.append(f"bing {key}: http={code}")
        time.sleep(1.0)
    # DuckDuckGo (202 が普通。来たら数える)
    code, body = curl("https://html.duckduckgo.com/html/?q="
                      + urllib.parse.quote("site:" + HOST))
    row["ddg_http"] = code
    row["ddg_mine"] = len(set(re.findall(re.escape(HOST) + r"/[a-zA-Z0-9%_.-]*", body)))
    if code not in (200, 202):
        bad.append(f"ddg http={code}")
    row["measure_ok"] = not bad
    row["bad"] = bad
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    if not quiet:
        print(f"  索入室の実測    : bing site: {row['bing_site_mine']} 面 (http {code and row['bing_site_http']})"
              + "".join(f" / {k} {row[f'bing_{k}_mine']}" for k, _ in EXACT)
              + f" / ddg {row['ddg_mine']} (http {row['ddg_http']})")
        if bad:
            print(f"    ★ 測れなかった: {bad[:3]}")
    return row


if __name__ == "__main__":
    r = probe()
    if not r["measure_ok"]:
        print("★★★ GUARD FAIL: index-probe — 索入室が測れない (クエリの形が壊れた可能性)")
        sys.exit(1)
    print("  索入室センサー OK (0 件は正常な状態として記録)")
