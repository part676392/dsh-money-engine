"""金の入口 (注文ボタン) を 1 個所にまとめる。

実測: 企業頁には注文ボタンを付けていたのに、人が最初に着く面には何も無かった。
  index.html  访问 17 件 / 注文 link 0
  question-lineups.html  5 件 / 0
  store/  4 件 / 0
つまり 26 人が「買う場所を探すページ」で買う場所を探していた。
この module を呼ぶ面を増やし、money_check の cta_check で毎巡回に確かめる。
"""
from __future__ import annotations

from urllib.parse import quote  # noqa: F401  (builder 側から使うことがあるので出して置く)

import order_link
from tracker_js import beacon_js

# 価格は build_dataset_store.TIER が単一の実装。ここでは文として書き出す (変更は両方見る)。
PRICE_LINE = ("1社だけ **$5** / 〜50社 $15 / 〜150社 $35 / 全社 473社 $60 / "
              "歴史スナップショット一式 $25")
ACCOUNT_NOTE = "注文には GitHub のアカウントがいります"

_CSS = ("display:inline-block;background:#0b6b3a;color:#fff;padding:9px 15px;"
        "border-radius:5px;font-weight:700;text-decoration:none")
_WRAP = ("margin:20px 0 0;padding:13px 15px;background:#fff;"
         "border:1px solid #e3e7ed;border-radius:6px")
_RAW = "color:#5b6570;font-size:.82rem;margin-left:10px;line-height:1.65"


def url(company: str = "", plan: str = order_link.ENTRY_PLAN) -> str:
    return order_link.url(company, plan)


def html(company: str = "", count_txt: str = "", cta: str = "") -> str:
    """面の末尾に置く注文欄。company を渡すとその会社名を form に预先入れる。"""
    u = url(company) if company else url()
    if not cta:
        cta = ("この会社ぶんを <b>$5</b> で受け取る" if company
               else "まず1社ぶんだけ <b>$5</b> で受け取る")
    note = ("開いた注文 form には会社名が既に入っています。" if company
            else "開いた注文 form で会社名と個数を選びます。")
    cnt = (count_txt + "・") if count_txt else ""
    return ("<p style='" + _WRAP + "'><a href='" + u.replace("&", "&amp;") +
            "' style='" + _CSS + "' onclick=\"" + beacon_js("order-click") +
            ";return true\">" + cta + "</a><span style='" + _RAW + "'>" + cnt +
            PRICE_LINE.replace("**", "") + "・出典URLつき。" + note +
            ACCOUNT_NOTE + "。</span></p>")


def inject(path, count_txt: str = "") -> bool:
    """書き出した html の </main> 直前に注文欄を足す。
    %書式や .format の template は {BUY} が展開されないので、後から差す方を信用する。"""
    import pathlib as _p
    fp = _p.Path(path)
    h = fp.read_text(encoding="utf-8")
    if "template=order.yml" in h:
        return False
    block = html(count_txt=count_txt)
    if "</main>" in h:
        h = h.replace("</main>", block + "</main>", 1)
    elif "</body>" in h:
        h = h.replace("</body>", block + "</body>", 1)
    else:
        return False
    fp.write_text(h, encoding="utf-8")
    return True
