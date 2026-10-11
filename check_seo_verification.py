#!/usr/bin/env python3
"""検索エンジン (Bing / Google) の所有権検証ファイルが『生きて』いるかを見る.

現状の実測 (2026-10-11): 索引されている私の頁は 0 面 (bing site: 0 面 / ddg 0 / Google 0)。
IndexNow は 200 を返しているので『投げていない』じゃない。 ここ から先は人間のログインが
要る扉なので、未取得を ★ にせず (事故ではないから) 『届いていない』として立て続ける。
ファイルが現たら: git に追跡されているか / 公開 URL で 200 か / 中身が一致するか を測る。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = "https://part676392.github.io/dsh-money-engine"
PATTERNS = ["BingSiteAuth.xml", "bing*.xml", "google*.html", "bfc*.html"]
HANDOFF = ROOT / "outbox" / "handoff-search.md"


def candidates() -> list[Path]:
    out: list[Path] = []
    for pat in ["BingSiteAuth.xml", "bing*.xml", "google*.html", "bfc*.html"]:
        for d in (ROOT, ROOT / "seo-verify"):
            out += sorted(d.glob(pat))
    return [p for p in out if p.is_file()]


def tracked(p: Path) -> bool:
    r = subprocess.run(["git", "ls-files", "--error-unmatch", str(p.relative_to(ROOT))],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0


def live(p: Path) -> tuple[int, str]:
    rel = str(p.relative_to(ROOT))
    url = f"{BASE}/{rel}"
    r = subprocess.run(["curl", "-s", "--max-time", "25", "-w", "\n%{http_code}", url],
                       capture_output=True, text=True)
    body, _, code = r.stdout.rpartition("\n")
    return (int(code) if code.isdigit() else 0), body.strip()


def check() -> bool:
    files = candidates()
    if not files:
        print("  検索の所有権検証  : 未取得 (人間のログインが 1 回要る扉 / 事故ではない)")
        print(f"    手順はここに置いてある: {HANDOFF.relative_to(ROOT)}"
              if HANDOFF.exists() else "    ★ handoff の手順書が無い")
        return True
    bad = []
    for p in files:
        rel = str(p.relative_to(ROOT))
        if not tracked(p):
            bad.append(f"{rel}: git に追跡されていない (push されず 404 になる)")
            continue
        code, body = live(p)
        raw = p.read_text(encoding="utf-8", errors="replace").strip()
        if code != 200:
            bad.append(f"{rel}: 公開 URL が HTTP {code}")
        elif raw and raw[:40] not in body.replace("\r", ""):
            bad.append(f"{rel}: 頁の中身がリポジトリと違う (HTTP {code})")
        else:
            print(f"    ✓ {rel}: HTTP {code} / 中身一致 ({len(raw)} 字)")
    if bad:
        print("  検索の所有権検証  : ★ " + " / ".join(bad[:3]))
        return False
    print(f"  検索の所有権検証  : OK ({len(files)} 個が配られている)")
    return True


if __name__ == "__main__":
    ok = check()
    if not ok:
        print("★★★ GUARD FAIL: seo-verify — 検証ファイルが有るのに配られていない / 中身が違う")
    sys.exit(0 if ok else 1)
