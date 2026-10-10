#!/usr/bin/env python3
"""AEO の主張を実測する監査器.

 README に「AEO 向け (JSON-LD / FAQ / ItemList)」と書いた。
 書いた以上、497 ページ全部で本当にそうか数える。
 一つでも parse できない JSON-LD があれば、その頁の構造化データは死んでいる。

 見るもの:
   - JSON-LD が parse できるか (生 text を json.loads する)
   - 型ごとの必須項目が欠けていないか
   - canonical / meta robots / title
   - サイト内リンクが実在する (relative link を:on HTML から辿る)
"""
from __future__ import annotations

import collections
import json
import pathlib
import re
import urllib.parse
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SITE_BASE = "dsh-money-engine"  # Pages project site の URL prefix

REQUIRED = {
    "ItemPage": ["mainEntity"],
    "Article": ["headline"],
    "FAQPage": ["mainEntity"],
    "ItemList": ["itemListElement"],
    "Dataset": ["name", "description"],
    "Service": ["name", "offers"],
    "Person": ["name"],
    "BreadcrumbList": ["itemListElement"],
    "WebSite": ["name", "url"],
}
BAD_TITLE = 70


def files() -> list:
    out = []
    for pat in ("*.html", "company/*.html", "store/*.html"):
        out += sorted(ROOT.glob(pat))
    return out


def ld_blocks(html: str) -> list:
    return re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)


def main() -> int:
    fs = files()
    total = len(fs)
    parse_fail = []
    missing_req = []
    types = collections.Counter()
    no_ld = []
    no_canonical = []
    no_robots = []
    long_title = []
    broken_links = collections.Counter()
    link_total = 0

    for f in fs:
        try:
            html = f.read_text(encoding="utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            parse_fail.append((str(f), f"read: {e}"))
            continue
        rel = str(f.relative_to(ROOT))
        blocks = ld_blocks(html)
        if not blocks:
            no_ld.append(rel)
        for b in blocks:
            try:
                d = json.loads(b)
            except Exception as e:  # noqa: BLE001
                parse_fail.append((rel, f"json: {str(e)[:60]}"))
                continue
            # index.html は @graph で束ねている (正当な JSON-LD). 展開して数える。
            if isinstance(d, dict) and "@graph" in d:
                items = d["@graph"]
            else:
                items = d if isinstance(d, list) else [d]
            for it in items:
                t = it.get("@type", "?")
                for name in ([t] if isinstance(t, str) else list(t)):
                    types[name] += 1
                    need = REQUIRED.get(name, [])
                    miss = [k for k in need if k not in it]
                    if miss:
                        missing_req.append((rel, name, miss))
        if 'rel="canonical"' not in html:
            no_canonical.append(rel)
        if 'name="robots"' not in html:
            no_robots.append(rel)
        m = re.search(r"<title>(.*?)</title>", html, re.S)
        if not m:
            long_title.append((rel, "no title", 0))
        elif len(m.group(1).strip()) > BAD_TITLE:
            long_title.append((rel, "long", len(m.group(1).strip())))
        for href in re.findall(r'href="([^"#?]+)"', html):
            if href.startswith(("http://", "https://", "mailto:", "//")):
                continue
            link_total += 1
            # href は percent-encode 済み (実測 live 200)。素のパスで見て
            # 「壊れてないのに壊れている」と嘘をついた (22件)。
            href_dec = urllib.parse.unquote(href)
            if href_dec.startswith("/"):
                # サイト根相対。Pages は /dsh-money-engine/ 配下なので、その
                # prefix を落としてから repo 根 (= サイト根) に解決する。
                # prefix を素でfilesystemに当てると「存在するのに壊れている」になる。
                rest = href_dec.lstrip("/")
                if rest.startswith(SITE_BASE + "/"):
                    rest = rest[len(SITE_BASE) + 1:]
                target = (ROOT / rest).resolve()
            else:
                target = (f.parent / href_dec).resolve()
            if href.endswith("/"):
                target = target / "index.html"
            if not target.exists():
                broken_links[href] += 1

    print(f"  files                : {total}")
    print(f"  JSON-LD blocks parsed: {sum(types.values())} typed entries, "
          f"{total - len(no_ld)}/{total} files carry JSON-LD")
    print(f"  types              : " + ", ".join(f"{k}={v}" for k, v in types.most_common(8)))
    print(f"  JSON-LD parse fail : {len(parse_fail)}" + (f"  ★ {parse_fail[:3]}" if parse_fail else ""))
    print(f"  files w/o JSON-LD  : {len(no_ld)}" + (f"  {no_ld[:4]}" if no_ld else ""))
    print(f"  missing required   : {len(missing_req)}" + (f"  ★ {missing_req[:2]}" if missing_req else ""))
    print(f"  missing canonical  : {len(no_canonical)}" + (f"  {no_canonical[:4]}" if no_canonical else ""))
    print(f"  missing meta robots: {len(no_robots)}" + (f"  {no_robots[:4]}" if no_robots else ""))
    print(f"  titles over {BAD_TITLE}   : {len(long_title)}" + (f"  {long_title[:2]}" if long_title else ""))
    print(f"  internal links     : {link_total} checked, {sum(broken_links.values())} broken "
          f"({len(broken_links)} distinct targets)")
    if broken_links:
        for t, n in broken_links.most_common(5):
            print(f"      ★ {t}  x{n}")
    verdict = not parse_fail and not missing_req and not broken_links and not no_ld
    print(f"\n  AEO claim holds: {verdict}")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
