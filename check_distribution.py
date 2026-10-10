#!/usr/bin/env python3
"""配布面が生きているか、リンクが落ちしていないかを無人で確認する.

 今日作って壊れたもの:
   - heredoc を 'EOF' で作らなかったせいで shell が $6 を展開し、
     配布ページの価格が空になった。作業者のシェル事故であって
     掲載先の不具合ではなかった。だからここで毎度 '価格が表示されているか' を見る。
   - Telegraph は access token を要求するようになった (Telegram 認可=人を要る)
   - Lemmy 0.19 は password_verify 必須、さらに captcha_incorrect
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent
HIST = ROOT / "data" / "distribution"
STORE_MARK = "part676392.github.io/dsh-money-engine/store"

SURFACES = [
    {"name": "gist", "url": None, "needs": [STORE_MARK]},
    {"name": "rentry_v2", "url": None, "needs": ["6 USD", STORE_MARK, "18+"]},
    {"name": "rentry_v3", "url": None, "needs": ["730 words", "Dryers on Carver Street",
                                                   "3 USD", "6 USD", "9 USD", STORE_MARK]},
    {"name": "dpaste", "url": None, "needs": ["Dryers on Carver Street", "3 USD", "6 USD",
                                              "9 USD", STORE_MARK, "0xA51eafFA2057"]},
]


def fetch(url: str) -> tuple:
    """本文と HTTP コードを一緒に返す.

    429 を「内容が消えた」と同一視するのは計器の嘘。rate limit は
    検証できなかったということで、死とは違う。2026-10-11 に dpaste で実演。
    """
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", "25", "-w", "\n__HTTP__%{http_code}", url],
            capture_output=True, text=True, timeout=30)
        body = r.stdout
        code = 0
        if "__HTTP__" in body:
            head, _, tail = body.rpartition("__HTTP__")
            code = int("".join(c for c in tail if c.isdigit()) or 0)
            body = head
        return body, code
    except Exception:  # noqa: BLE001
        return "", 0


def load_urls() -> None:
    g = ROOT / "data" / "gist_url.txt"
    if g.exists():
        for s in SURFACES:
            if s["name"] == "gist":
                s["url"] = g.read_text(encoding="utf-8").strip()
    rj = ROOT / "data" / "rentry.json"
    if rj.exists():
        d = json.loads(rj.read_text(encoding="utf-8"))
        for s in SURFACES:
            if s["name"] == "rentry_v2":
                s["url"] = d.get("v2_url") or d.get("url")
            if s["name"] == "rentry_v3":
                s["url"] = d.get("v3_url")
            if s["name"] == "dpaste":
                s["url"] = json.loads((ROOT / "data" / "dpaste.json").read_text(
                    encoding="utf-8")).get("url") if (ROOT / "data" / "dpaste.json").exists() else None


PR_WATCH = ROOT / "data" / "pr_watches.json"


def pr_watch() -> dict:
    """他所の repo に出した PR の生死 (merge されたか).

    gh の認証が通る場所だけが使える導線。2026-10-11 に awesome-open-data へ
    PR #57 を出した (昨日も merge されている活性リストだと確認してから)。
    merge されれば人間が辿れる場所に常設の被リンクが残る。
    """
    if not PR_WATCH.exists():
        return {}
    res = {}
    for it in json.loads(PR_WATCH.read_text(encoding="utf-8")):
        ref = f"{it['repo']}#{it['number']}"
        jq = '.state + " " + (.merged_at // "-") + " " + (.comments|tostring)'
        cmd = ["gh", "api", f"repos/{it['repo']}/pulls/{it['number']}", "--jq", jq]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        except Exception as e:
            res[ref] = {"error": str(e)[:90]}
            print(f"  PR {ref:40s} 取得失敗 {str(e)[:60]}")
            continue
        if r.returncode != 0:
            res[ref] = {"error": (r.stderr or "").strip()[:90]}
            print(f"  PR {ref:40s} 取得失敗 {(r.stderr or '').strip()[:56]}")
            continue
        parts = (r.stdout.strip().split(" ") + ["-", "-", "-"])[:3]
        state, merged, comments = parts
        res[ref] = {"state": state, "merged_at": None if merged == "-" else merged,
                    "comments": comments, "url": it.get("url", "")}
        print(f"  PR {ref:40s} {'★★★ MERGED' if merged != '-' else state}"
              f"  comments={comments}")
    return res


def main() -> int:
    HIST.mkdir(parents=True, exist_ok=True)
    load_urls()
    out = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "surfaces": {}}
    ok_all = True
    unverified = []
    for s in SURFACES:
        if not s["url"]:
            print(f"  {s['name']:10s} SKIP (url 未記録)")
            ok_all = False
            continue
        h, code = fetch(s["url"])
        present = [n for n in s["needs"] if n in h]
        missing = [n for n in s["needs"] if n not in present]
        rate_limited = code in (429,) or code >= 500
        good = len(present) == len(s["needs"]) and len(h) > 800
        if rate_limited and not good:
            # 消えたのかнялかを区別できないので ✗ にしない。☆ で出す。
            mark = "☆"
            unverified.append(s["name"])
            print(f"  {mark} {s['name']:10s} bytes={len(h):6d} http={code} "
                  f"VERIFY PENDING (rate limited, not treated as dead)")
        else:
            mark = "✓" if good else "✗"
            ok_all = ok_all and good
            print(f"  {mark} {s['name']:10s} bytes={len(h):6d} http={code} ok={good}"
                  + (f" missing={missing}" if missing else ""))
        print(f"      {s['url']}")
        out["surfaces"][s["name"]] = {"url": s["url"], "bytes": len(h), "http": code,
                                      "ok": good, "missing": missing,
                                      "rate_limited": rate_limited}
    if unverified:
        print(f"\n  検証保留 (rate limited, 死とは別): {unverified}")
    out["pull_requests"] = pr_watch()
    merged = [k for k, v in out["pull_requests"].items() if v.get("merged_at")]
    if merged:
        print(f"\n  ★★★ PR merged: {merged}")
    (HIST / "latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    with open(HIST / f"{time.strftime('%Y-%m-%d-%H%M')}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n  all surfaces live: {ok_all}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
