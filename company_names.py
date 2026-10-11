#!/usr/bin/env python3
"""会社の名前ゆれを揃える。揃っていないと同じ会社の頁が分裂して、搜いた人に一部の載った1頁が当たる。

実測 (2026-10-11): company/*.html 491 頁を作っていたが、名前ゆれで 9 組が分裂していた。
  4 頁: JR西日本（西日本旅客鉄道） / JR西日本（西日本旅客鉄道株式会社）
        / 西日本旅客鉄道（JR西日本） / 西日本旅客鉄道株式会社（JR西日本）
  3 頁: 東日本旅客鉄道（JR東日本） / JR東日本（東日本旅客鉄道株式会社） / 「　東日本旅客鉄道株式会社（JR東日本）」
        ※ 先頭に全角スペースが付いた名前が 8 件あった (note の記事タイトル由来)
束ねると 479 社。束ねる規則は機械的に決める (人が勘で寄せない)。
"""
from __future__ import annotations

import collections
import re
import unicodedata

_WS = re.compile(r"^[\s\u3000]+|[\s\u3000]+$")
_IN = re.compile(r"[\s\u3000]+")
_PAREN = re.compile(r"^(.+?)[(（](.+?)[)）]$")


def norm(n: str) -> str:
    """全角/半角・空白・株式会社 を落とした比較用の名前。"""
    s = unicodedata.normalize("NFKC", n or "")
    s = _WS.sub("", s)
    s = _IN.sub("", s)
    s = re.sub(r"^株式会社", "", s)
    s = re.sub(r"\(株\)|（株）$", "", s)
    s = re.sub(r"株式会社$", "", s)
    return s


def token_key(n: str):
    """`X（Y）` と `Y（X）` を同じ key にする。括号の無い名前は自分自身と対応。"""
    s = norm(n)
    m = _PAREN.match(s)
    if m:
        a = re.sub(r"株式会社$", "", m.group(1))
        b = re.sub(r"株式会社$", "", m.group(2))
        if a and b:
            return frozenset({a, b})
    return frozenset({s or n})


def canon_map(names):
    """name -> 正規化名。同じ token key の中から一番長い (情報が一番多い) 名前を使う。"""
    groups = collections.defaultdict(list)
    for n in names:
        if not n:
            continue
        groups[token_key(n)].append(n)
    out, canon_of = {}, {}
    for key, grp in groups.items():
        # 先頭に全角スペースが付いた名前 (記事タイトル由来) を正規化に選ばない。
        # 順位: 空白の無いもの > 長いもの (情報量) > 辞書順。
        def rank(x):
            ws = 1 if x != x.strip() or x.startswith("\u3000") else 0
            return (ws, -len(x), x)
        best = sorted(grp, key=rank)[0]
        canon_of[best] = best
        for n in grp:
            canon_of[n] = best
        out[best] = sorted({n for n in grp if n != best})
    return canon_of, out


if __name__ == "__main__":
    names = ["JR西日本（西日本旅客鉄道）", "西日本旅客鉄道株式会社（JR西日本）",
             "　東日本旅客鉄道株式会社（JR東日本）", "JR東日本（東日本旅客鉄道株式会社）",
             "株式会社ディスコ", "　株式会社ディスコ", "森永製菓", "森永製菓株式会社"]
    cm, alias = canon_map(names)
    for n in names:
        print(f"  {n!r:44s} -> {cm[n]!r}")
    print("  groups:", {k: v for k, v in alias.items() if v})
