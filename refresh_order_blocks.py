#!/usr/bin/env python3
"""全站のメール口 (mailto) を今のコードで作り直す sweep。

実測 (2026-10-11): buy_block.mailto_link の既定 tier を『1社ぶん ($5)』→ form と同じ
『1社だけ試す ($5)』に直しても、full loop を回した後で 11 頁に古い語が残った。
  ai-interviews / changes / deliveries / interview-questions / question-lineups /
  reverse-questions / sample / selection-flows / selection-signals / store/index / store/mini
→ These surfaces get their order block from a one-off refresh, not from a builder that
   calls inject(), so the copy rotted. ここが毎巡回で回す。
"""
from __future__ import annotations

import pathlib
import sys

import buy_block

ROOT = pathlib.Path(__file__).resolve().parent
STALE_MARK = "1%E7%A4%BE%E3%81%B6%E3%82%93"   # 『1社ぶん』の URL encode


def dirs():
    out = sorted(ROOT.glob("*.html")) + sorted((ROOT / "store").glob("*.html"))
    out += sorted((ROOT / "company").glob("*.html"))
    return out


def main() -> int:
    files, touched, links, stale = 0, 0, 0, []
    for f in dirs():
        files += 1
        try:
            n = buy_block.refresh_mail(f)
        except Exception as e:                       # noqa: BLE001
            print(f"  ★ {f.name}: {e}")
            return 1
        links += n
        touched += 1 if n else 0
        if STALE_MARK in f.read_text(encoding="utf-8", errors="replace"):
            stale.append(f.name)
    print(f"  メール口の作り直し : {files:,} 頁を見て {touched} 頁 / href {links} 本を差し替え"
          f" / 古い語の残る {len(stale)} 頁" + (f" {stale[:5]}" if stale else ""))
    if stale:
        print("★★★ GUARD FAIL: mail-copy — 古い料金語のメール口が残っている")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
