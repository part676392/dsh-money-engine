#!/usr/bin/env python3
"""金銭ページ (store/, store/mini.html) の受注に必要な物が揃っているか守る.

 動機: 先に自分の probe が '$' しか探さず、mini の '3 USD' 表記を見落とした。
 値札・送り先・支払い段取り・語数の段のどれか一つでも欠けると、
 読者は買いたくても買えない。だから毎巡回で実 HTML を引き直して検査する。

 検査するもの (全部 生きた HTTP 応答に対して):
   1. 価格 (\\$6 か "6 USD" かの両方を受け取る)
   2. 送り先メール (受信箱 address)
   3. 暗号 address (0x...)
   4. 支払いの順序が読める ("pay" と "email"/"send" の両方)
   5. 語数の段が parser の TIERS と一致する
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent
BASE = "https://part676392.github.io/dsh-money-engine"
PAGES = ["store/", "store/mini.html"]


def tiers() -> dict:
    src = (ROOT / "check_orders.py").read_text(encoding="utf-8")
    m = re.search(r"TIERS = (\{[^}]+\})", src)
    return eval(m.group(1)) if m else {}


def fetch(p: str) -> str:
    r = subprocess.run(["curl", "-s", "--max-time", "25", f"{BASE}/{p}"],
                       capture_output=True, text=True, timeout=32)
    return r.stdout


def has_price(text: str, usd: int) -> bool:
    return bool(re.search(rf"\$\s?{usd}\b", text) or re.search(rf"\b{usd}\s*(?:USD|usd|ドル)", text))


def main() -> int:
    tr = tiers()
    inbox = ""
    wfile = ROOT / "outbox" / "mailtm.json"
    addr = ""
    if wfile.exists():
        inbox = json.loads(wfile.read_text(encoding="utf-8")).get("address", "")
    wfile2 = ROOT / "outbox" / "wallet.json"
    if wfile2.exists():
        addr = json.loads(wfile2.read_text(encoding="utf-8")).get("address", "")
    rows = []
    all_ok = True
    for p in PAGES:
        raw = fetch(p)
        text = re.sub(r"<[^>]+>", " ", raw)
        t = re.sub(r"\s+", " ", text)
        prices = sorted({int(x) for x in re.findall(r"\$\s?(\d{1,2})\b", t)} |
                        {int(x) for x in re.findall(r"\b(\d{1,2})\s*(?:USD|usd)\b", t)} |
                        {int(x) for x in re.findall(r"\b(\d{1,2})\s*ドル", t)})
        checks = {
            "bytes": len(raw),
            "prices": prices,
            "inbox": bool(inbox) and inbox in t,
            "wallet": bool(addr) and addr in t,
            "how_to_pay": bool(re.search(r"\b(pay|送金)\b", t, re.I)) and
                          bool(re.search(r"\b(email|send|注文)\b", t, re.I)),
            "words_stated": bool(re.search(r"\b\d{1},?\d{3}\s*(?:words|word|語)", t)),
        }
        # parser の段が公開頁のどこかに全部出ているか (mini 側に来ているので合算で見る)
        rows.append((p, checks))
        if len(raw) < 2000:
            print(f"  ★ {p}: 応答が短い ({len(raw)}B) — 配信事故の可能性")
            all_ok = False
        if not checks["inbox"] or not checks["wallet"]:
            print(f"  ★ {p}: 送り先が足りない inbox={checks['inbox']} wallet={checks['wallet']}")
            all_ok = False
    # 段の突合は全頁合わせて
    joined = " ".join(re.sub(r"<[^>]+>", " ", fetch(p)) for p in PAGES)
    missing = [f"{w}→${v}" for w, v in tr.items() if not has_price(joined, v)]
    if missing:
        print(f"  ★ parser の段が公開頁に無い: {', '.join(missing)}")
        all_ok = False
    print(f"  checked at {time.strftime('%Y-%m-%d %H:%M:%S')}  pages={len(PAGES)}")
    for p, c in rows:
        print(f"    {p:16s} {c['bytes']:>6,}B  prices={c['prices']} inbox={c['inbox']} "
              f"wallet={c['wallet']} pay_steps={c['how_to_pay']} words={c['words_stated']}")
    print(f"  parser tiers: {tr}")
    print(f"  公開価格の突合: {'PASS' if not missing else 'FAIL ' + str(missing)}")
    print(f"\n  money pages ready: {all_ok}")
    out = ROOT / "data" / "rails" / "money_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                              "pages": dict(rows), "parser_tiers": tr,
                              "missing_tiers": missing, "ready": all_ok},
                             ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
