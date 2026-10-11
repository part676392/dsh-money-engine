#!/usr/bin/env python3
"""注文 form への link。prefill の鍵は GitHub の仕様で field の `id`。

企業頁から飛んだ人に会社名を入力させない (実測: 注文の形が分からず止まる人がいる前提で、
入口は短いほどいい)。`plan` には form の選択肢そのものを入れる (選択肢と違う文字列は
黙って選択されない。.guard で突合する)。
"""
from __future__ import annotations

import urllib.parse

ISSUES = "https://github.com/part676392/dsh-money-engine/issues/new"
ENTRY_PLAN = "1社だけ試す ($5)"


# 『注文だったが金が入らず閉じた』状態の語。旧字 (閉結) は私の造語で日本語として変なので
# 不成立 に変えたが、台帳 data/deliveries.json には 2026-10-11 までの旧値が残っている。
CLOSED_WORDS = ("不成立", "閉結")


def is_closed(status) -> bool:
    """台帳の status が『閉じた注文』を指すか (旧値も読む)。"""
    txt = str(status or "")
    return any(w in txt for w in CLOSED_WORDS)


def url(company: str = "", plan: str = "", title: str = "") -> str:
    q = {"template": "order.yml"}
    if title:
        q["title"] = title
    elif company:
        q["title"] = f"注文: {company} ぶん"
    if plan:
        q["plan"] = plan
    if company:
        q["companies"] = company
    return ISSUES + "?" + urllib.parse.urlencode(q)


if __name__ == "__main__":
    print(" ", url("JR西日本（西日本旅客鉄道株式会社）", ENTRY_PLAN))
