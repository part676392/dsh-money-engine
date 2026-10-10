#!/usr/bin/env python3
"""受注口(匿名受信箱)が生きているか確かめ、死んでいたら作り直して再公開する.

 理由: 金の漏斗で唯一の単一障害点はこれ。mail.tm は使い捨て運用なので、
 アカウントが消えると買い主のメールが无声で失われる。何も音がならない。
 なので毎朝 token を取り直して、取れなければ作り直す。
 作り直したら setAddress が載った頁を再公開しないと意味がないので、
 store 2 枚の再生成 + 配布面の再掲 + push + Pages ビルドまでやる。
"""
from __future__ import annotations

import json
import pathlib
import secrets
import string
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent
CRED = ROOT / "outbox" / "mailtm.json"
B = "https://api.mail.tm"
STORE = "https://part676392.github.io/dsh-money-engine/store/"


def api(method: str, path: str, body: dict | None = None, tok: str = "") -> tuple:
    args = ["curl", "-s", "--max-time", "25", "-X", method, B + path,
            "-H", "Content-Type: application/json"]
    if body:
        args += ["-d", json.dumps(body)]
    if tok:
        args += ["-H", f"Authorization: Bearer {tok}"]
    r = subprocess.run(args, capture_output=True, text=True, timeout=32)
    try:
        return json.loads(r.stdout), r.stdout
    except Exception:  # noqa: BLE001
        return {}, r.stdout


def token(addr: str, pw: str) -> str:
    j, _ = api("POST", "/token", {"address": addr, "password": pw})
    return j.get("token", "")


def create_mailbox() -> dict:
    j, _ = api("GET", "/domains")
    mem = j.get("hydra:member") or []
    if not mem:
        raise RuntimeError("mail.tm domains が取得できない")
    domain = mem[0]["domain"]
    user = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(9))
    pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(14)) + "!A7"
    addr = f"{user}@{domain}"
    res, raw = api("POST", "/accounts", {"address": addr, "password": pw})
    if not res.get("id"):
        raise RuntimeError(f"mailbox 作成失敗: {str(raw)[:120]}")
    return {"address": addr, "password": pw, "domain": domain}


def republish(addr: str) -> None:
    """setAddress が載った頁を作り直す (store 2 枚 + 配布面)."""
    for script in ("build_store.py", "build_mini.py", "build_site.py"):
        p = ROOT / script
        if p.exists():
            r = subprocess.run(["python3", str(p)], capture_output=True, text=True, timeout=120)
            last = (r.stdout or "").strip().splitlines()
            print(f"    {script}: {(last[-1] if last else 'no output')[:90]}")
    page = (ROOT / "rentry_order.md")
    text = page.read_text(encoding="utf-8") if page.exists() else ""
    if not text:
        text = ("# Explicit fiction written to your specification\n\n"
                "You send characters, situation, tone, hard limits. "
                "You get a finished explicit scene as a text file. "
                "No fade to black. All characters 25 or older.\n\n"
                "Prices: 700 words - 3 USD / 1,500 words - 6 USD / 2,500 words - 9 USD. "
                "One free revision if a named limit is missed.\n\n"
                f"Order by email, then pay the crypto address on the store page "
                f"(Base, Arbitrum, Polygon or Ethereum).\n\n"
                f"Current order address: {addr}\n\n"
                f"Free full example and address: [store page]({STORE})\n\nAdults 18+.\n")
    text = text.replace("CURRENT_ADDRESS", addr) if "CURRENT_ADDRESS" in text else text
    tmp = ROOT / "outbox" / "rentry-current.md"
    tmp.write_text(text.replace(STORE, STORE) if addr in text else text, encoding="utf-8")
    # -F "text=@file" はアップロード扱いで rentry に弾かれる。"text=<file" は
    # 中身をプレーン field にする (2026-10-11 実測)。
    r = subprocess.run(["curl", "-s", "--max-time", "40", "-F", f"text=<{tmp}",
                        "https://rentry.co/api/new"], capture_output=True, text=True, timeout=60)
    try:
        d = json.loads(r.stdout)
        print(f"    rentry: {d.get('url') or d.get('content')}")
        if d.get("url"):
            rec_f = ROOT / "data" / "rentry.json"
            rec = json.loads(rec_f.read_text(encoding="utf-8")) if rec_f.exists() else {}
            rec["v_live"] = d["url"]
            rec["v_live_created"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            rec_f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001
        print(f"    rentry fail: {r.stdout[:90]}")


def push() -> None:
    subprocess.run(["git", "add", "-A"], cwd=ROOT, capture_output=True)
    d = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT, capture_output=True)
    if d.returncode != 0:
        subprocess.run(["git", "-c", "user.name=part676392",
                        "-c", "user.email=72697109+part676392@users.noreply.github.com",
                        "commit", "-qm", "受注口を自己修復: 新受信箱を再発行し頁を再公開"],
                       cwd=ROOT, capture_output=True)
        tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "push", "-q",
                        f"https://x-access-token:{tok}@github.com/part676392/dsh-money-engine.git",
                        "HEAD:main"], cwd=ROOT, capture_output=True)
        subprocess.run(["gh", "api", "-X", "POST",
                        "repos/part676392/dsh-money-engine/pages/builds"],
                       cwd=ROOT, capture_output=True)
        print("    pushed + pages rebuild")
    else:
        print("    no file change")


def main() -> int:
    if not CRED.exists():
        print("  outbox/mailtm.json が無い -> 新規発行")
        m = create_mailbox()
        m["created"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        CRED.parent.mkdir(parents=True, exist_ok=True)
        CRED.write_text(json.dumps(m, indent=1), encoding="utf-8")
        republish(m["address"])
        push()
        print(f"  ★ 新受注口 {m['address']}")
        return 0

    c = json.loads(CRED.read_text(encoding="utf-8"))
    tok = token(c.get("address", ""), c.get("password", ""))
    if tok:
        j, _ = api("GET", "/messages", tok=tok)
        print(f"  ✓ 受注口 生存 {c['address']} (messages={j.get('hydra:totalItems')})")
        return 0

    print("  ✗ 受注口 死亡 (token 取得失敗)。自己修復する")
    m = create_mailbox()
    m["created"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    m["replaced"] = c.get("address")
    CRED.write_text(json.dumps(m, indent=1), encoding="utf-8")
    republish(m["address"])
    push()
    print(f"  ★ 新受注口 {m['address']} (旧 {m['replaced']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
