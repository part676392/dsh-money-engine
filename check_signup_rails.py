#!/usr/bin/env python3
"""読者が居る媒体の「入口が開いたか」を見張る.

 2026-10-11 に測った壁 (全部実物DOM/実POST):
   dev.to : メール登録に reCAPTCHA。POST してもトークン長 0 で作れない
   Qiita  : hCaptcha が登録画面にある
   Zenn   : GitHub OAuth のみ。こちらのブラウザに GitHub セッションが無い
   HN     : POST の返答が "Sorry, account creation disabled."

 これらは人力で一度やれば終わるものばかりなので、**開いた合図**を機械に出す。
 開いていたら日次ログに ★ を出す。
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent
HIST = ROOT / "data" / "rails"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


def get(url: str, extra: list | None = None) -> tuple:
    args = ["curl", "-s", "--max-time", "25", "-A", UA, url] + (extra or [])
    r = subprocess.run(args, capture_output=True, text=True, timeout=30)
    return r.stdout


def hn() -> dict:
    """HN は実登録を試みる. GET では開いているか閉じているか分からない (2026-10-11 実測).

    GET の login 頁は create form を常に出すので、GET だけ見た計器は OPEN と誤爆した。
    本当は POST して "account creation disabled" が返るかでしか分からない。
    開いていればそのまま垢ができるので、そのほうが嬉しい。
    """
    f = ROOT / "outbox" / "hn-account.txt"
    if not f.exists():
        return {"error": "outbox/hn-account.txt が無い"}
    lines = f.read_text(encoding="utf-8").split()
    if len(lines) < 2:
        return {"error": "hn-account.txt の形が違う"}
    acct, pw = lines[0], lines[1]
    jar = "/tmp/hn-jar.txt"
    get("https://news.ycombinator.com/login", ["-c", jar])
    body = subprocess.run(
        ["curl", "-s", "--max-time", "25", "-A", UA, "-b", jar, "-c", jar,
         "--data-urlencode", "creating=t",
         "--data-urlencode", f"acct={acct}",
         "--data-urlencode", f"pw={pw}",
         "https://news.ycombinator.com/login"],
        capture_output=True, text=True, timeout=30).stdout
    low = body.lower()
    # 理由を必ず一行で残す。「disabled じゃない＝開いてる」ではない (taken がある)。
    msg = ""
    m = re.search(r"(Sorry|That username|must be|too many)[^<]{0,80}", body)
    if m:
        msg = m.group(0)[:90]
    else:
        plain = re.sub(r"<[^>]+>", " ", body)
        msg = re.sub(r"\s+", " ", plain).strip()[:70]
    logged = "logout" in low
    return {"attempted_as": acct, "creation_disabled": "account creation disabled" in low,
            "message": msg, "logged_in": logged, "open": logged}


def devto() -> dict:
    body = get("https://dev.to/users/sign_up?state=email_signup")
    captcha = bool(re.search(r"recaptcha|g-recaptcha-response|hcaptcha", body, re.I))
    form = 'name="user[username]"' in body
    return {"email_form": form, "captcha_present": captcha, "open": form and not captcha}


def qiita() -> dict:
    body = get("https://qiita.com/signup")
    captcha = bool(re.search(r"hcaptcha|recaptcha|turnstile", body, re.I))
    form = 'name="user[email]"' in body
    return {"email_form": form, "captcha_present": captcha, "open": form and not captcha}


def reddit() -> dict:
    """Reddit は最後に測った実登録の記録を出す.

    2026-10-11 実測: email/username/password は埋まり submit も走るが、
    `google.com/recaptcha/enterprise/anchor` が読まれ /register に留まる。
    エラー文も確認メール案内も出ない = captcha で止められている。
    reCAPTCHA Enterprise は画像解読なので、この環境では越えられない。
    """
    f = ROOT / "outbox" / "reddit-signup.json"
    if not f.exists():
        return {"error": "outbox/reddit-signup.json が無い (signup_reddit.js を実行)"}
    d = json.loads(f.read_text(encoding="utf-8"))
    cap = "recaptcha/enterprise" in json.dumps(d.get("requests", []))
    return {"attempted_at": d.get("at", ""), "username": d.get("username"),
            "verdict": d.get("verdict"), "recaptcha_enterprise": cap, "open": False,
            "blocked_by": "reCAPTCHA Enterprise" if cap else str(d.get("verdict"))}


def main() -> int:
    HIST.mkdir(parents=True, exist_ok=True)
    rows = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "hn": hn(), "devto": devto(), "qiita": qiita(), "reddit": reddit()}
    opened = [k for k, v in rows.items() if isinstance(v, dict) and v.get("open")]
    for k in ("hn", "devto", "qiita", "reddit"):
        v = rows[k]
        state = "OPEN ★" if v.get("open") else "blocked"
        detail = " ".join(f"{a}={b}" for a, b in v.items())
        print(f"  {k:6s} {state:9s} {detail}")
    print(f"\n  opened: {opened or 'none — 人間が一度 captcha を押せば開く場所が5つ'}")
    (HIST / "signup_latest.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
