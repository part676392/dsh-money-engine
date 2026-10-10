#!/usr/bin/env python3
"""mail.tm に使い捨て mailbox をもう一つ作って outbox に保存する.

 目的: 媒体の登録にはメール確認が要る。受信箱を用途別に分けて、
 一つの垢が死んでも他が死ぬのを防ぐ (前に一度で全部詰まりかけた)。
"""
from __future__ import annotations

import json
import pathlib
import secrets
import string
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
B = "https://api.mail.tm"


def curl(args: list, timeout: int = 25) -> tuple:
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout)] + args,
                       capture_output=True, text=True, timeout=timeout + 6)
    try:
        return json.loads(r.stdout), r.stdout[:160]
    except Exception:  # noqa: BLE001
        return {}, r.stdout[:160]


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else "misc"
    out = ROOT / "outbox" / f"mailtm-{tag}.json"
    if out.exists():
        d = json.loads(out.read_text(encoding="utf-8"))
        tok, raw = curl(["-X", "POST", f"{B}/token", "-H", "Content-Type: application/json",
                         "-d", json.dumps({"address": d["address"], "password": d["password"]})])
        if tok.get("token"):
            print(f"  既存が生きてる: {d['address']}")
            return 0

    doms, raw = curl([f"{B}/domains"])
    members = doms.get("hydra:member") or []
    if not members:
        print(f"  domain 取得失敗: {raw}")
        return 1
    domain = members[0]["domain"]
    alpha = string.ascii_lowercase + string.digits
    local = tag[:4].rstrip("0123456789") + "".join(secrets.choice(alpha) for _ in range(7))
    addr = f"{local}@{domain}"
    pw = "Mx" + "".join(secrets.choice(alpha) for _ in range(13)) + "9"
    body = json.dumps({"address": addr, "password": pw})
    acc, raw = curl(["-X", "POST", f"{B}/accounts", "-H", "Content-Type: application/json", "-d", body])
    if not acc.get("id"):
        print(f"  account 作成失敗: {raw}")
        return 1
    tok, raw = curl(["-X", "POST", f"{B}/token", "-H", "Content-Type: application/json",
                     "-d", json.dumps({"address": addr, "password": pw})])
    if not tok.get("token"):
        print(f"  token 取得失敗: {raw}")
        return 1
    out.write_text(json.dumps({"address": addr, "password": pw, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                              "token_len": len(tok.get("token", ""))}, indent=1), encoding="utf-8")
    out.chmod(0o600)
    print(f"  created: {addr}  (token ok)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
