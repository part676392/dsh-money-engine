#!/usr/bin/env python3
"""公開済みの面に ?src=<key> 付きURLを打ち直す (流入源の分離).

 実測: 访问 home=4 store=3 license=4 sample=1 で、全部自分の訪問。
 どの面から人が来たか、ずっと unknown だった。
 頁側の JS は ?src= を読んで src-<key> にも hit を置くようになったので、
 ここでは外に出した URL を打ち直す作業だけをする。
 全部自分の所有物 (自分の repo / 自分の gist / 自分の PR) に限定する。
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SITE = "https://part676392.github.io/dsh-money-engine"
GIST = "8f51111c9ac743c672cf3a04ed863fcf"
REPO = "part676392/dsh-money-engine"
PRS = {"pr57": "okhosting/awesome-open-data", "pr32": "taishi-i/awesome-japanese-nlp-resources"}
PRNUM = {"pr57": "57", "pr32": "32"}


def gh(*args: str) -> tuple:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=90)
    return r.returncode, (r.stdout or r.stderr).strip()


def url(target: str, key: str) -> str:
    sep = "&" if "?" in target else "?"
    return f"{SITE}/{target}{sep}src={key}"


def main() -> int:
    tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True,
                         timeout=30).stdout.strip()
    if not tok:
        print("  ★★★ gh token が空")
        return 1
    done, skipped = [], []

    # 1) README: 先頭の live リンクだけ打つ (本文の構造的な link は無印のまま)
    rd = ROOT / "README.md"
    t = rd.read_text(encoding="utf-8")
    pat = re.compile(r"\[[^\]]+\]\(" + re.escape(SITE + "/") + r"\)")
    if "](" + SITE + "/?src=ghrepo)" in t:
        skipped.append("README 済み")
    elif pat.search(t):
        t2 = pat.sub(f"[Live site — 目録データベース]({url('index.html', 'ghrepo')})", t, count=1)
        rd.write_text(t2, encoding="utf-8")
        assert "src=ghrepo" in rd.read_text(encoding="utf-8")
        done.append("README")
    else:
        skipped.append("README に裸の site link が無い")

    # 2) 最新の release 本文
    rc, tag = gh("release", "list", "--repo", REPO, "--limit", "1", "--json", "tagName",
                 "--jq", ".[0].tagName")
    if rc == 0 and tag.startswith("snap-"):
        rc2, body = gh("api", f"repos/{REPO}/releases/tags/{tag}", "--jq", ".body")
        if "src=release" in body:
            skipped.append("release 済み")
        else:
            nb = (body + f"\n\n---\n納品物見本 (3社ぶん実物): {url('sample.html', 'release')}\n"
                        f"目録: {url('index.html', 'release')}\n")
            rc3, out = gh("api", "-X", "PATCH", f"repos/{REPO}/releases/{tag.strip()}",
                          "-f", f"body={nb}")
            # release id が欲しいので tag 検索でなく id を取る
            if rc3 != 0:
                rc4, rid = gh("api", f"repos/{REPO}/releases/tags/{tag}", "--jq", ".id")
                rc3, out = gh("api", "-X", "PATCH", f"repos/{REPO}/releases/{rid}",
                              "-f", f"body={nb}")
            if rc3 == 0:
                rc5, back = gh("api", f"repos/{REPO}/releases/tags/{tag}", "--jq", ".body")
                (done if "src=release" in back else skipped).append("release " + ("確認" if "src=release" in back else "★ 未反映"))
            else:
                skipped.append(f"release ★ {out[:60]}")
    else:
        skipped.append("release 取得失敗")

    # 3) 自分の PR 本文 (相手は編集権を渡していない自分の PR)
    for key, repo in PRS.items():
        rc, body = gh("api", f"repos/{repo}/pulls/{PRNUM[key]}", "--jq", ".body // \"\"")
        if rc != 0:
            skipped.append(f"{key} ★ 読めない")
            continue
        if "src=" + key in body:
            skipped.append(f"{key} 済み")
            continue
        nb = body.rstrip() + f"\n\nData page (with source tag so I can tell where clicks come from): {url('index.html', key)}\n"
        rc2, out = gh("api", "-X", "PATCH", f"repos/{repo}/pulls/{PRNUM[key]}",
                      "-F", f"body={nb}")
        if rc2 == 0:
            rc3, back = gh("api", f"repos/{repo}/pulls/{PRNUM[key]}", "--jq", ".body")
            (done if ("src=" + key) in back else skipped).append(
                f"{key} " + ("確認" if ("src=" + key) in back else "★ 未反映"))
        else:
            skipped.append(f"{key} ★ {out[:70]}")

    # 4) gist 本文
    rc, raw = gh("api", f"gists/{GIST}")
    if rc == 0:
        try:
            g = json.loads(raw)
            fname = next(iter(g.get("files", {}).keys()), None)
            cur = g.get("files", {}).get(fname, {}).get("content", "")
        except Exception as e:  # noqa: BLE001
            fname, cur = None, ""
            print(f"  ★ gist parse: {str(e)[:60]}")
        if fname and "src=gist" not in cur:
            nb = cur.rstrip() + f"\n\nData page: {url('index.html', 'gist')}\nSample CSV: {url('exports/questions_catalog.csv', 'gist')}\n"
            payload = json.dumps({"files": {fname: {"content": nb}}})
            r = subprocess.run(["gh", "api", "-X", "PATCH", f"gists/{GIST}",
                                "--input", "-"], input=payload, capture_output=True,
                               text=True, timeout=90)
            if r.returncode == 0:
                rc2, back = gh("api", f"gists/{GIST}", "--jq",
                               f".files[].content")
                (done if "src=gist" in back else skipped).append(
                    "gist " + ("確認" if "src=gist" in back else "★ 未反映"))
            else:
                skipped.append(f"gist ★ {r.stderr[:70]}")
        elif fname:
            skipped.append("gist 済み")

    print(f"  打ち直し完了: {', '.join(done) if done else '無し'}")
    if skipped:
        print(f"  スキップ/要確認: {', '.join(skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
