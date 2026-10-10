#!/usr/bin/env python3
"""匿名受信箱を受注口として無人で見る.

 mail.tm は受信できる。つまり API が読める。
 買主は s8l...@maxxspace.com へ仕様を送り、俺はここで拾って配送する。
 バックエンドもフォームも人の協力も要らない。
 前回の自分の失敗: token を保存して使い回した。mail.tm の token は
 1 時間で失効するので、毎回 password から取り直す。
"""
from __future__ import annotations

import base64
import json
import pathlib
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent
CRED = ROOT / "outbox" / "mailtm.json"
HIST = ROOT / "data" / "orders"
B = "https://api.mail.tm"


def curl(args: list, timeout: int = 25) -> tuple:
    try:
        r = subprocess.run(["curl", "-s", "--max-time", str(timeout)] + args,
                           capture_output=True, text=True, timeout=timeout + 6)
        return r.stdout, None
    except Exception as e:  # noqa: BLE001
        return "", str(e)[:80]


def token(addr: str, pw: str) -> str:
    body = json.dumps({"address": addr, "password": pw})
    out, err = curl(["-X", "POST", f"{B}/token", "-H", "Content-Type: application/json", "-d", body])
    try:
        return json.loads(out).get("token", "")
    except Exception:  # noqa: BLE001
        print(f"  token failed: {err or out[:80]}")
        return ""


def messages(tok: str) -> list:
    out, err = curl(["-H", f"Authorization: Bearer {tok}", f"{B}/messages"])
    try:
        return json.loads(out).get("hydra:member", [])
    except Exception:  # noqa: BLE001
        print(f"  inbox read failed: {err or out[:80]}")
        return []


def message_detail(tok: str, mid: str) -> dict:
    out, _ = curl(["-H", f"Authorization: Bearer {tok}", f"{B}/messages/{mid}"])
    try:
        return json.loads(out)
    except Exception:  # noqa: BLE001
        return {}


def seen_ids() -> set:
    f = HIST / "seen.json"
    if f.exists():
        try:
            return set(json.loads(f.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            return set()
    return set()


def main() -> int:
    if not CRED.exists():
        print("  no mailtm.json")
        return 0
    c = json.loads(CRED.read_text(encoding="utf-8"))
    addr, pw = c.get("address", ""), c.get("password", "")
    HIST.mkdir(parents=True, exist_ok=True)

    tok = token(addr, pw)
    if not tok:
        print("  could not get token (mailbox may have expired; recreate with mailtm setup)")
        return 0
    msgs = messages(tok)
    seen = seen_ids()
    fresh = [m for m in msgs if m.get("id") not in seen]
    print(f"  inbox: {len(msgs)} message(s), unseen: {len(fresh)}")

    orders = []
    for m in fresh[:6]:
        d = message_detail(tok, m["id"])
        text = (d.get("text") or "").strip()
        html_body = d.get("html") or []
        if not text and html_body:
            raw = html_body[0] if isinstance(html_body, list) else str(html_body)
            try:
                raw = base64.b64decode(raw).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                pass
            import re as _re
            text = _re.sub(r"<[^>]+>", " ", raw)
        rec = {
            "id": m.get("id"),
            "from": (m.get("from") or {}).get("address"),
            "subject": m.get("subject"),
            "received": m.get("createdAt"),
            "intro": " ".join(text.split())[:280],
        }
        orders.append(rec)
        print(f"  ★ ORDER from {rec['from']}  «{rec['subject']}»")
        print(f"          {rec['intro'][:150]}")

    seen |= {m["id"] for m in msgs}
    (HIST / "seen.json").write_text(json.dumps(sorted(seen)), encoding="utf-8")
    if orders:
        with open(HIST / "orders.jsonl", "a", encoding="utf-8") as f:
            for o in orders:
                f.write(json.dumps(o, ensure_ascii=False) + "\n")
    (HIST / "latest.json").write_text(json.dumps(
        {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "total": len(msgs),
         "unseen": len(fresh), "orders": orders}, ensure_ascii=False, indent=1), encoding="utf-8")
    if not fresh:
        print("  no new orders yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
