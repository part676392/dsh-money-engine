"""金の入口 (注文欄) を 1 個所にまとめる。

企業のページには注文欄を付けていたのに、人が最初に着く面には何も無かった。
  index.html             访问 17 件 / 注文の導線 0
  question-lineups.html  访问  5 件 / 0
  store/                 訪問  4 件 / 0
導線を全頁へ差した次は、位置が嘘だった。
  index.html 145,446 字のうち注文欄は 99% 目 (最後の最後) に在った
  上部に有ったのは『データ資産の購入』の迂回 link だけで、注文 form への直線は無かった
だから bar() (h1 の直下) と html() (頁末) の 2 種類を出す。
どちらも money_check.cta_check で毎巡回点検する (位置も含める)。
"""
from __future__ import annotations

from urllib.parse import quote  # noqa: F401  (builder 側から使うことがあるので出して置く)

import order_link
from tracker_js import beacon_js

# 価格は build_dataset_store.TIER が単一の実装。ここでは文として書き出す (変更は両方見る)。
PRICE_LINE = ("1社だけ **$5** / 〜50社 $15 / 〜150社 $35 / 全社 473社 $60 / "
              "歴史スナップショット一式 $25")
ACCOUNT_NOTE = "注文には GitHub のアカウントがいります"

# 支払いの口の実測 (2026-10-11): 料金を出す 7 面にカード link は 0 本。Gumroad の管理画面が
# 自分の言葉で止まっていた: "You haven't connected a payout method yet, so you won't be able
# to publish this product for sale." 受取方法 (銀行) の登録は人の仕事なので、嘘を書かない。
HONEST = "カード決済はまだ用意できていません"
CARD_NOTE = ("支払い: 暗号送金 (Base / Arbitrum / Polygon / ETH) か、この帳簿への GitHub 注文。"
             + HONEST + " (受取方法の登録を Gumroad が要求していて、そこだけ人が 1 分やる必要)。"
             "送金だけの方でも注文 form を出せばこっちで合わせます。")
_CARD_WRAP = ("margin:8px 0 0;padding:8px 12px;background:#f2f5f9;border:1px solid #dfe5ec;"
              "border-radius:6px;font-size:.8rem;color:#5b6570;line-height:1.65")


def card_note() -> str:
    return "<p style='" + _CARD_WRAP + "'>" + CARD_NOTE + "</p>"

_CSS = ("display:inline-block;background:#0b6b3a;color:#fff;padding:9px 15px;"
        "border-radius:5px;font-weight:700;text-decoration:none")
_WRAP = ("margin:20px 0 0;padding:13px 15px;background:#fff;"
         "border:1px solid #e3e7ed;border-radius:6px")
_RAW = "color:#5b6570;font-size:.82rem;margin-left:10px;line-height:1.65"
_BAR_WRAP = ("margin:10px 0 0;padding:9px 12px;background:#fff7e8;"
             "border:1px solid #e8c98a;border-radius:6px;font-size:.92rem;line-height:1.7")
_BAR_A = "color:#8a4b00;font-weight:700;text-decoration:none"


def url(company: str = "", plan: str = order_link.ENTRY_PLAN) -> str:
    return order_link.url(company, plan)


def _cta_text(company: str) -> str:
    return ("この会社ぶんを <b>$5</b> で受け取る" if company
            else "まず1社ぶんだけ <b>$5</b> で受け取る")


def _free_sample(company: str) -> str:
    # 常に絶対道。store/ の頁で href="sample.html" にすると store/sample.html に
    # 解決されて 404 になった (実測: internal links 10 折れ / ★ sample.html x10)。
    label = ("他の会社の無料サンプル" if company else "無料サンプル (実文を先に見る)")
    return ('<a style="' + _BAR_A + '" href="/dsh-money-engine/sample.html">' + label + "</a>")


def html(company: str = "", count_txt: str = "") -> str:
    """頁の末尾に置く注文欄。company を渡すとその会社名を form に预先入れる。"""
    u = (url(company) if company else url()).replace("&", "&amp;")
    note = ("開いた注文 form には会社名が既に入っています。" if company
            else "開いた注文 form で会社名と個数を選びます。")
    cnt = (count_txt + "・") if count_txt else ""
    return ("<p style='" + _WRAP + "'><a href='" + u + "' style='" + _CSS +
            "' onclick=\"" + beacon_js("order-click") + ";return true\">" +
            _cta_text(company) + "</a><span style='" + _RAW + "'>" + cnt +
            PRICE_LINE.replace("**", "") + "・出典URLつき。" + note +
            ACCOUNT_NOTE + "。</span></p>")


def bar(company: str = "") -> str:
    """h1 の直下 (最初の1画面) に置く短い注文欄。読まずに買えるようにする。"""
    u = (url(company) if company else url()).replace("&", "&amp;")
    return ("<p style='" + _BAR_WRAP + "'>💴 <a style='" + _BAR_A + "' href='" + u +
            "' onclick=\"" + beacon_js("order-click") + ";return true\">" +
            _cta_text(company) + "</a>　" + PRICE_LINE.replace("**", "") +
            "　·　" + _free_sample(company) + "　·　" + ACCOUNT_NOTE + "</p>")


def inject(path, count_txt: str = "", top: str = "") -> bool:
    """書き出した html に注文欄を足す。
    %書式や .format の土台は {BUY} が展開されないので、後から差す方を信用する。
    top を渡すと </h1> の直後にも上部欄を差す (実測: 注文欄が 99% 目にしか無かった)。"""
    import pathlib as _p
    fp = _p.Path(path)
    h = fp.read_text(encoding="utf-8")
    changed = False
    if top and "</h1>" in h and "template=order.yml" not in h.split("</h1>")[0]:
        h = h.replace("</h1>", "</h1>" + bar(top), 1)
        changed = True
    if "template=order.yml" not in h:
        block = html(count_txt=count_txt)
        if "</main>" in h:
            h = h.replace("</main>", block + "</main>", 1)
        elif "</body>" in h:
            h = h.replace("</body>", block + "</body>", 1)
        else:
            return changed
        changed = True
    if changed:
        fp.write_text(h, encoding="utf-8")
    return changed
