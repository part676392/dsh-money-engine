#!/usr/bin/env python3
"""暗号受金口の残高を無人でwatchし、変化を history に積む.

 前段の失敗: ethers の JsonRpcProvider が応答なしでハングした。
 そこで curl に任せて python には待たせない。各 RPC に固い timeout。
 1 件も応答が無くても exit 0（監視の停止が誤って失敗扱いにならないように）。
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent
WALLET = ROOT / "outbox" / "wallet.json"
HIST = ROOT / "data" / "payments"

RPCS = [
    ("base", "https://mainnet.base.org"),
    ("arbitrum", "https://arb1.arbitrum.io/rpc"),
    ("polygon", "https://polygon-bor-rpc.publicnode.com"),
    ("optimism", "https://mainnet.optimism.io"),
]


def balance(chain: str, url: str, addr: str) -> dict:
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "eth_getBalance", "params": [addr, "latest"]}
    ).encode()
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "12", "-X", "POST", url,
             "-H", "Content-Type: application/json", "-d", body.decode()],
            capture_output=True, text=True, timeout=16,
        )
        out = r.stdout.strip()
        if not out:
            return {"chain": chain, "ok": False, "why": "empty"}
        j = json.loads(out)
        if "result" in j:
            wei = int(j["result"], 16)
            return {"chain": chain, "ok": True, "wei": wei, "eth": wei / 1e18}
        return {"chain": chain, "ok": False, "why": str(j.get("error"))[:80]}
    except Exception as e:  # noqa: BLE001
        return {"chain": chain, "ok": False, "why": str(e)[:70]}


def main() -> int:
    if not WALLET.exists():
        print("  no wallet.json")
        return 0
    addr = json.loads(WALLET.read_text(encoding="utf-8")).get("address", "")
    if not addr:
        print("  wallet has no address")
        return 0

    HIST.mkdir(parents=True, exist_ok=True)
    prev_f = HIST / "latest.json"
    prev = json.loads(prev_f.read_text(encoding="utf-8")) if prev_f.exists() else {"chains": {}}

    res = {}
    for chain, url in RPCS:
        b = balance(chain, url, addr)
        res[chain] = b
        flag = ""
        if b.get("ok"):
            old = (prev.get("chains", {}).get(chain) or {}).get("wei", 0)
            if b["wei"] != old:
                flag = f"  ← CHANGED from {old / 1e18:.6f}"
            print(f"  {chain:9s} {b['eth']:.6f} ETH{flag}")
        else:
            print(f"  {chain:9s} unreachable ({b.get('why')})")
        time.sleep(0.3)

    got = [v for v in res.values() if v.get("ok")]
    incoming = [c for c, v in res.items() if v.get("ok") and v["wei"] > (prev.get("chains", {}).get(c, {}).get("wei", 0))]
    snap = {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "address": addr,
        "chains": res,
        "rpcs_ok": len(got),
        "total_eth": sum(v.get("eth", 0) for v in got),
        "incoming_on": incoming,
    }
    (HIST / "latest.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(HIST / f"{time.strftime('%Y-%m-%d-%H%M')}.json", "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)

    if incoming:
        print(f"\n  ★ PAYMENT DETECTED on {incoming}")
    else:
        print(f"\n  no incoming movement. rpc ok={len(got)}/{len(RPCS)} total={snap['total_eth']:.6f} ETH")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
