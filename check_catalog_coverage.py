#!/usr/bin/env python3
"""company_pages.csv が 公開中の企業頁を全部載せているかの護り。

実測 (2026-10-11): sitemap には 473 頁立っていたのに company_pages.csv は 457 行への link しか
持っておらず、16 頁 (JERAインターン / アビーム 戦略コンサルタントコース / DTFA など 選考段階の
言及だけの会社の頁) が表から消えていた。CSV を落とした人には「その頁は存在しない」のと同じ。
表は頁的全量である、という不変条件を機械で見る。
"""
from __future__ import annotations

import csv
import pathlib
import re
import subprocess
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent
BASE = "https://part676392.github.io/dsh-money-engine"


def fetch(path: str, binary: bool = False) -> str:
    r = subprocess.run(["curl", "-sL", "--max-time", "30", f"{BASE}/{path}"],
                       capture_output=True, text=True, timeout=40)
    return r.stdout or ""


def page_name(url: str) -> str:
    # live の sitemap は <loc> が改行で囲われている (実測で </loc> が名前に残った)
    tail = urllib.parse.unquote((url or "").split("/company/")[-1])
    tail = re.sub(r"</loc>\s*$", "", tail).strip()
    return tail[:-5].strip() if tail.endswith(".html") else tail


def main() -> int:
    sm = fetch("sitemap.xml")
    if "<urlset" not in sm:
        print("    目録と頁の対応  : ★ sitemap.xml が読めない")
        return 1
    urls = re.findall(r"<loc>\s*([^<]*/company/[^<]*?)\s*</loc>", sm)
    sitemap = {page_name(u) for u in urls}
    raw = fetch("exports/company_pages.csv")
    if not raw.strip():
        print("    目録と頁の対応  : ★ company_pages.csv が読めない")
        return 1
    rows = list(csv.DictReader(raw.splitlines()))
    linked = {page_name(r.get("page_url") or "") for r in rows if (r.get("page_url") or "").strip()}
    missing = sorted(sitemap - linked)
    # manifest の行数と実行数がズレると、页数を公称している側が嘘になる
    man = fetch("exports/manifest.csv")
    man_rows = {r.get("file"): r.get("rows") for r in csv.DictReader(man.splitlines())} if man else {}
    claim = (man_rows.get("company_pages.csv") or "").replace(",", "")
    bad = []
    if missing:
        bad.append(f"頁はあるが表に無い {len(missing)} 件: {[x[:22] for x in missing[:4]]}")
    if claim and claim != str(len(rows)):
        bad.append(f"manifest は {claim} 行 / CSV 実 {len(rows)} 行")
    ok = not bad
    tail = (f"  (sitemap {len(sitemap)} 頁 / 表 {len(rows)} 行 / link 付き {len(linked)})")
    print(f"    目録と頁の対応  : {'OK' if ok else '★ ' + '; '.join(bad)}{tail}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
