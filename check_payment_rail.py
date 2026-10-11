#!/usr/bin/env python3
"""支払いレールの生存を機械に確かめる.

 2026-10-11 に測った事実:
   - Gumroad の垢作成と製品作成は captcha も電話も個人情報も要らなかった。
   - ただし payout (銀行 / PayPal) を繋ぐまで製品は "not currently for sale" になる。
     payout は人の資産に紐づくので、代理人の判断で勝手に繋がない。
   - だからこの計器は **レールが開いた瞬間** を見張る。開いたら logos に出る。

 暗号レールは即金で開いている (4 chain RPC で残高を見る)。
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent
HIST = ROOT / "data" / "rails"
GUM = ROOT / "outbox" / "gumroad.json"
FOR_SALE_MARK = "not currently for sale"


def fetch(url: str) -> tuple:
    r = subprocess.run(["curl", "-sL", "--max-time", "25", "-w", "\n__HTTP__%{http_code}", url],
                       capture_output=True, text=True, timeout=30)
    body, code, out = r.stdout, 0, r.stdout
    if "__HTTP__" in body:
        head, _, tail = body.rpartition("__HTTP__")
        code = int("".join(c for c in tail if c.isdigit()) or 0)
        out = head
    return out, code


def crypto() -> dict:
    chains = {"base": "https://mainnet.base.org",
              "arbitrum": "https://arb1.arbitrum.io/rpc",
              "polygon": "https://polygon-rpc.com",
              "optimism": "https://mainnet.optimism.io"}
    addr = ""
    wf = ROOT / "outbox" / "wallet.json"
    if wf.exists():
        addr = json.loads(wf.read_text(encoding="utf-8")).get("address", "")
    total, ok = 0, 0
    for name, url in chains.items():
        try:
            r = subprocess.run(["curl", "-s", "--max-time", "12", "-X", "POST", url,
                                "-H", "Content-Type: application/json",
                                "-d", f'{{"jsonrpc":"2.0","id":1,"method":"eth_getBalance",'
                                      f'"params":["{addr}","latest"]}}'],
                               capture_output=True, text=True, timeout=14)
            j = json.loads(r.stdout)
            if "result" in j:
                wei = int(j["result"], 16)
                total += wei / 1e18
                ok += 1
        except Exception:  # noqa: BLE001
            continue
    return {"address": addr, "rpc_ok": f"{ok}/4", "total_eth": round(total, 6),
            "live": total > 0}


def gumroad() -> dict:
    """Gumroad の販売状態はブラウザで見る.

    curl だと React が water する前の HTML を読むことになり、
    "not currently for sale" が本文に出ないので OPEN と誤爆した (2026-10-11 実測)。
    """
    if not GUM.exists():
        return {"configured": False}
    r = subprocess.run(["node", str(ROOT / "rail_probe.js")],
                       capture_output=True, text=True, timeout=140)
    try:
        d = json.loads(r.stdout)
    except Exception:  # noqa: BLE001
        # 探測が壊れた時 (node  NotFound / network / rate limit) に key が無いと、
        # 下で KeyError -> 護りが crash -> 巡回全体が money で止まった (2026-10-11 実測)。
        # だから「不明」を形で返す。
        return {"configured": True, "probe_failed": True, "for_sale": False,
                "blocked_by_payout": None, "http": None, "price_shown": "",
                "buy_buttons": None, "card_field": None, "url": None,
                "error": (r.stderr or r.stdout or "探測が無何も返さなかった")[:160]}
    return {
        "configured": True,
        "url": d.get("url"),
        "http": d.get("http"),
        "price_shown": (d.get("price_shown") or [""])[0],
        "blocked_by_payout": d.get("blocked_by_payout"),
        "buy_buttons": d.get("buy_buttons"),
        "card_field": (d.get("card_stage") or {}).get("hasCardField"),
        "for_sale": bool(d.get("for_sale")),
    }


def main() -> int:
    HIST.mkdir(parents=True, exist_ok=True)
    c = crypto()
    g = gumroad()
    print(f"  crypto  : {c['rpc_ok']} rpc  total={c['total_eth']} ETH  "
          f"{'★ PAYMENT' if c['live'] else 'no movement'}")
    if g.get("configured"):
        if g.get("probe_failed"):
            # 外部の問い合せ失敗は自分の劣化ではないので止まらない。だが ★ で残す。
            print(f"  gumroad : ★ 探測失敗 — 購入可否は不明 ({g.get('error','')})")
        else:
            state = "OPEN (buyable)" if g["for_sale"] else (
                "CLOSED — payout not connected" if g["blocked_by_payout"]
                else f"UNKNOWN http={g.get('http')}")
            print(f"  gumroad : http={g.get('http')} price={g.get('price_shown')}  {state}")
            print(f"      {g.get('url')}")
            if g["for_sale"]:
                print("  ★★★ CARD RAIL OPEN — 店の頁にカード導線を載せてよい")
    else:
        print("  gumroad : 未設定 (outbox/gumroad.json)")
    out = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "crypto": c, "gumroad": g}
    (HIST / "latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(HIST / f"{time.strftime('%Y-%m-%d-%H%M')}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
