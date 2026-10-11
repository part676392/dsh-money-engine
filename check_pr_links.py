#!/usr/bin/env python3
"""唯一 人が辿れている入口 (開いてる PR 本文の link) が生きているかの点検。

実測 (2026-10-11): 計数は src-pr32=32 / src-jopendata=10 / src-pr57=8 で、
home 28 を上回る量が PR 由来なのに、PR 本体は一度も点検していなかった。
誰かが本文を編集しても・クローズしても黙っている (計数が落ちるまで分からない)。

  taishi-i/awesome-japanese-nlp-resources#32   src=pr32
  okhosting/awesome-open-data#57               src=pr57
  japan-opendata/awesome-japan-opendata#30     src=jopendata
"""
from __future__ import annotations

import json
import subprocess
import sys

SITE = "part676392.github.io/dsh-money-engine"

PRS = [
    ("taishi-i/awesome-japanese-nlp-resources", 32, "src=pr32"),
    ("okhosting/awesome-open-data", 57, "src=pr57"),
    ("japan-opendata/awesome-japan-opendata", 30, "src=jopendata"),
]


def gh_json(*args: str) -> tuple:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=70)
    if r.returncode != 0:
        return None, r.stderr.strip()
    try:
        return json.loads(r.stdout), ""
    except Exception as e:      # 読めない物は読めないと言う
        return None, f"json: {e}"


def check(quiet: bool = False) -> dict:
    rows, bad = [], []
    for repo, num, tag in PRS:
        d, err = gh_json("api", f"repos/{repo}/pulls/{num}")
        if not d:
            bad.append(f"{repo}#{num} が読めない: {err[:60]}")
            rows.append({"repo": repo, "num": num, "state": "unreadable"})
            continue
        body = d.get("body") or ""
        st = d.get("state") or "?"
        if d.get("merged_at"):
            st = "merged"
        elif st == "closed":
            bad.append(f"{repo}#{num} が閉じられた (link 消失)")
        n_tag, n_site = body.count(tag), body.count(SITE)
        if n_tag <= 0:
            bad.append(f"{repo}#{num} の本文に {tag} が無い")
        rows.append({"repo": repo, "num": num, "state": st, "body": len(body),
                     "tag": n_tag, "site": n_site, "title": (d.get("title") or "")[:24]})
    if not quiet:
        for r in rows:
            if r["state"] == "unreadable":
                print(f"    {r['repo']}#{r['num']:<3} ★ 読めない")
                continue
            print(f"    {r['repo']}#{r['num']:<3} {r['state']:<7} 本文 {r['body']:,}字"
                  f" / {tag_of(r)} / 自ドメイン link {r['site']} 本")
        print("  PR 入口          : " + ("OK" if not bad else "★ " + "; ".join(bad[:2]))
              + f" ({len(PRS)} 先)")
    return {"rows": rows, "bad": bad}


def tag_of(row: dict) -> str:
    for repo, num, tag in PRS:
        if row["repo"] == repo and row["num"] == num:
            return f"{tag} ×{row['tag']}"
    return "?"


if __name__ == "__main__":
    st = check()
    if st["bad"]:
        print("★★★ GUARD FAIL: pr-links — 人が辿れている入口の link が消えたか読めない")
        sys.exit(1)
