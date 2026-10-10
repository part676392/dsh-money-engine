#!/usr/bin/env python3
"""公開 repo に秘密が混ざっていないか毎巡回で守る.

 動機: 今日の実測で、.gitignore に失敗して平文 password と JWT が
 public repo に commit されていたのを見つけた (`outbox/mailtm-lemmy.json` 他)。
 mail.tm は password の回転が効かない (PATCH/PUT が 405)。だから
 **混ぜない**以外の防御がなく、混ぜた瞬間に気づく巡回が要る。

 二つ見る:
   1. git に追跡されているファイルの中身に秘密語Patternsが無いこと
   2. outbox/ の実ファイルが全部 gitignore で覆われていること
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent
SECRET_KEYS = ("password", "passwd", "secret", "api_key", "apikey", "access_token",
               "refresh_token", "authorization", "cookie")
JWT = re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")
PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


def tracked() -> list:
    r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, timeout=30)
    return [l for l in r.stdout.splitlines() if l.strip()]


def ignored(path: str) -> bool:
    r = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, timeout=20)
    return r.returncode == 0


def main() -> int:
    files = tracked()
    hits = []
    scanned = 0
    for rel in files:
        f = ROOT / rel
        if not f.exists() or f.is_dir():
            continue
        if f.stat().st_size > 400_000:
            continue
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        scanned += 1
        low = t.lower()
        for k in SECRET_KEYS:
            # 説明文 (rails 表・この巡回自身の docstring・README) は許す: 値が同じ行に無い
            for m in re.finditer(rf"[\"']?{k}[\"']?\s*[:=]\s*[\"']([^\"'\s]{{4,}})", low):
                val = m.group(1)
                if val in ("", "none", "null", "***", "…"):
                    continue
                if "example" in val or "your" in val or "$" in val or "{" in val:
                    continue
                hits.append((rel, k, val[:22]))
        if JWT.search(t) and "jwt.example" not in t:
            for m in JWT.finditer(t):
                if len(m.group(0)) > 40:
                    hits.append((rel, "jwt", m.group(0)[:22]))
                    break
        if PRIVATE_KEY.search(t):
            hits.append((rel, "private_key", "PEM"))

    outbox = sorted(p for p in (ROOT / "outbox").glob("*") if p.is_file())
    # 的内容を見て公開すると決めた原稿だけ Exceptions。無い物は全部失敗にする。
    BENIGN = {"brief_uncensored.txt", "brief_アビームコンサルティングの.txt",
              "copy_アビームコンサルティングの.json", "rentry-current.md",
              "uncensored_raw.txt"}
    uncovered = [p.name for p in outbox
                 if p.name not in BENIGN and not ignored(str(p.relative_to(ROOT)))]
    benign_tracked = [p.name for p in outbox if p.name in BENIGN]

    print(f"  scanned tracked files: {scanned} / {len(files)}")
    print(f"  secret-like hits     : {len(hits)}")
    for h in hits[:8]:
        print(f"      ★ {h[0]}  {h[1]}={h[2]}")
    print(f"  outbox files         : {len(outbox)}  gitignore 未覆: {len(uncovered)} "
          f"(公開決めてる原稿 {len(benign_tracked)} は除外して数える)")
    for u in uncovered[:8]:
        print(f"      ★ 未覆: {u}")
    ok = not hits and not uncovered
    print(f"\n  no secret in public repo: {ok}")
    out = ROOT / "data" / "rails" / "secrets_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scanned": scanned, "tracked_total": len(files),
        "hits": [list(h) for h in hits[:20]],
        "uncovered": uncovered, "clean": ok}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
