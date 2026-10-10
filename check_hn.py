#!/usr/bin/env python3
"""HN の Show HN 解禁を監視し、解禁したら本題を1本投稿する.

 実測 (2026-10-11 06:25): /r に Show HN を出すと 302 で showlim に飛んだ。
 本文は「大量流入の一時的制限。まず good contributor になってから」。
 出せないものを覚えさせておくのは自分なので、解禁判定を code に持たせる。
 投稿は高々1回。data/rails/hn_latest.json に item id を書いて二度と打たない。
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import time
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "data" / "rails"
JAR = "/tmp/hn_check.jar"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CRED = ROOT / "outbox" / "hn-account.txt"
STATE = OUT / "hn_latest.json"
TITLE = "Show HN: 1,873 real Japanese interview questions, indexed by company"
URL = "https://part676392.github.io/dsh-money-engine/?src=hn"


SIGNAL = {"showlim": "Show HN 一時制限 (平台側の大量流入対策)",
          "story-toofast": "新規垢の投稿間隔制限 (story-toofast)",
          "toofast": "投稿間隔制限"}


def mean_of(dest: str) -> str:
    for k, v in SIGNAL.items():
        if k in (dest or ""):
            return v
    if "item?id=" in (dest or ""):
        return "投稿が通った (item に飛んだ)"
    return "unknown"


def cred() -> tuple:
    t = CRED.read_text(encoding="utf-8").split()
    return t[0], t[1]


def curl(*args: str, hdr: bool = False) -> str:
    a = ["curl", "-s", "-c", JAR, "-b", JAR, "--max-time", "35", "-A", UA]
    if hdr:
        a.append("-i")
    r = subprocess.run(a + list(args), capture_output=True, text=True, timeout=50)
    return r.stdout


def main() -> int:
    if not CRED.exists():
        print("  hn-account.txt が無い")
        return 1
    user, pw = cred()
    os.makedirs(OUT, exist_ok=True)
    prev = {}
    if STATE.exists():
        try:
            prev = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            prev = {}

    out = curl("https://news.ycombinator.com/login", "-d",
               urllib.parse.urlencode({"acct": user, "pw": pw, "goto": "news"}), hdr=True)
    logged = "logout" in curl("https://news.ycombinator.com/news")
    prof = curl(f"https://news.ycombinator.com/user?id={user}")
    vis = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", prof))
    karma = (re.search(r"karma:\s*(-?\d+)", vis) or [None, "?"])[1]
    created = ((re.search(r"created:\s*(\d+\s*(?:minute|hour|day)s? ago)", vis) or [None, ""])[1]).strip()

    # 文字列 "0" が真になって「投稿済み」と誤判定した (実測)。HN の item id は 5 桁以上。
    raw_item = str(prev.get("posted_item_id") or "")
    item = raw_item if raw_item.isdigit() and len(raw_item) >= 5 else None
    posted = bool(item)
    dest = prev.get("probe_dest", "")
    if not posted:
        sub = curl("https://news.ycombinator.com/submit")
        m = re.search(r'name="fnid" value="([^"]+)"', sub)
        fnid = m.group(1) if m else ""
        fnop = (re.search(r'name="fnop" value="([^"]+)"', sub) or [None, "submit-page"])[1]
        if not fnid:
            print("  ★ submit form が取れない (login 失敗かBAN)")
            return 1
        r = curl("https://news.ycombinator.com/r", "-d",
                 urllib.parse.urlencode({"fnid": fnid, "fnop": fnop,
                                         "title": TITLE, "url": URL}), hdr=True)
        head = r.split("\r\n\r\n", 1)[0]
        dest = (re.search(r"[Ll]ocation: (\S+)", head) or [None, ""])[1]
        blocked = "showlim" in dest
        # 通った場合 HN は item 頁か news へ返す。item id が取れれば投稿成立。
        # 本文の "item?id=" を拾うと submit form 自身の link で誤検出した (実測)。
        # Location ヘッダに出た item id だけを成立とする。
        mm = re.search(r"item\?id=(\d+)", dest)
        if not blocked and mm:
            if len(mm.group(1)) >= 5:
                item, posted = mm.group(1), True
        print(f"  投稿 probe: → {dest or '-'}  → {mean_of(dest)}")
    else:
        print(f"  投稿済み (item {item}): 二度打たない")

    # 実害なしで产量 only を測る: 自分の comments 頁を見に行く
    cl = curl("https://news.ycombinator.com/submitted?id=%s&type=comments" % user)
    # ヘッダの self link を数えると常に 1 になる。本文 (commtext) を数える。
    n_comments = len(re.findall(r"class=\"commtext\"", cl))

    why = mean_of(dest) if not posted else "投稿済み"
    d = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "user": user,
         "login": logged, "karma": karma, "created": created,
         "posted_item_id": item, "probe_dest": dest, "title": TITLE, "url": URL,
         "dest_meaning": mean_of(dest), "comments_visible": n_comments,
         "policy": (f"{why}。comments 頁に {n_comments} 件 (投稿は 302 を返すが作られない)"
                    if not posted else "投稿済み")}
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  HN user={user} login={logged} karma={karma} created={created}")
    print(f"  状態: {d['policy']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
