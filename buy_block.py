"""金の入口 (注文欄) を 1 個所にまとめる。

企業のページには注文欄を付けていたのに、人が最初に着く面には何も無かった。
  index.html             訪問 17 件 / 注文の導線 0
  question-lineups.html  訪問  5 件 / 0
  store/                 訪問  4 件 / 0
導線を全頁へ差した次は、位置が嘘だった。
  index.html 145,446 字のうち注文欄は 99% 目 (最後の最後) に在った
  上部に有ったのは『データ資産の購入』の迂回 link だけで、注文 form への直線は無かった
だから bar() (h1 の直下) と html() (頁末) の 2 種類を出す。
どちらも money_check.cta_check で毎巡回点検する (位置も含める)。
"""
from __future__ import annotations

import html as _html
import pathlib
import re
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


def esc(s: object) -> str:
    return _html.escape(str(s), quote=True)


HISTORY_WORDS = ("台帳", "履歴", "観測")


def history_block() -> str:
    """$25 の『歴史スナップショット一式』の中身を実測の manifest から書く。
    店に値段だけ置いて中身が読めないのは嘘になるので、行数と link を一緒に出す。"""
    import csv
    p = pathlib.Path(__file__).resolve().parent / "exports" / "manifest.csv"
    if not p.exists():
        return ""
    rows = []
    with p.open(encoding="utf_8_sig", newline="") as fh:
        for r in csv.DictReader(fh):
            f, n, what = r.get("file"), r.get("rows"), r.get("content") or ""
            if f and any(w in what for w in HISTORY_WORDS):
                rows.append((f, n, what))
    if not rows:
        return ""
    links = " ／ ".join(
        '<a href="/dsh-money-engine/exports/%s">%s</a> (%s 行)' % (esc(f), f, esc(str(n) if str(n).isdigit() else "—"))
        for f, n, what in rows)
    return ('<div class="free"><b>歴史スナップショット一式 ($25) の中身</b>: %s<br>'
            '<span style="font-size:.8rem;color:#6d675e">毎巡回で積んでいるので、面に出た日がそのまま残ります。'
            '行の数はこの頁を書いた時点の実測です。</span></div>') % links


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


BLOCK_OPEN = "<!--buy-block-->"
BLOCK_CLOSE = "<!--/buy-block-->"

MAIL_NOTE = "GitHub 要らずで注文: 会社名と個数をメールで送るだけ (受信箱は毎巡回で読む)"


def inbox() -> str:
    """受信箱の addr。gitignore 下の outbox から読む (公開面に出すのは addresses だけ)。"""
    import json
    for rel in ("outbox/mailtm.json", "outbox/mailtm-devto.json"):
        f = pathlib.Path(__file__).resolve().parent / rel
        if f.exists():
            try:
                a = json.loads(f.read_text(encoding="utf-8")).get("address", "")
                if a:
                    return a
            except Exception:
                continue
    return ""


def mailto_link(company: str = "", tier: str = order_link.ENTRY_PLAN) -> str:
    """3 番目の支払い口 (メール)。GitHub のアカウントもカードも要らない。
    実測: order-click は 3 件で全部こちらの点検。人が click しやすい口を増やす。"""
    to = inbox()
    if not to:
        return ""
    # tier は form の選択肢と一字一句揃える (実測: 「1社ぶん ($5)」でメールし、form には
    # 「1社だけ試す ($5)」しか無い、という食い違いが有った。単一の源 = order_link.ENTRY_PLAN)
    subj = "注文: " + tier + (" / " + company if company else "")
    body = ("会社名: " + (company or "(ここに入れます)") + "\n"
            + "個数: " + tier + "\n"
            + "支払い: 暗号送金 (Base / Arbitrum / Polygon / ETH)、または送金後にこのメールへ tx を貼ります\n"
            + "欲しい物: 面接質問の実文と出典URLつきの CSV\n")
    href = "mailto:" + to + "?subject=" + quote(subj) + "&body=" + quote(body)
    return ('<a style="' + _BAR_A + '" href="' + href.replace("&", "&amp;") +
            '" onclick="' + beacon_js("order-mail") + ';return true">📧 メールで注文</a>')


def deadline_link(company: str = "") -> str:
    """締切一覧への直線。実測で link を持つのは 3 頁だけで、473 の企業頁から行けなかった。
    人が着くのは企業頁の方なので、上の行に置く。"""
    # 計数の穴: 上部欄 link のうち注文 link だけ beacon を持っていた
    # (実測: 締切頁 32 load で、どの link を踏んだか分からなかった)。
    return ('<a style="' + _BAR_A + '" href="/dsh-money-engine/es-deadlines.html"'
            ' onclick="' + beacon_js("cta-deadlines") + ';return true">⏰ 締切一覧</a>')


def _free_sample(company: str) -> str:
    # 常に絶対道。store/ の頁で href="sample.html" にすると store/sample.html に
    # 解決されて 404 になった (実測: internal links 10 折れ / ★ sample.html x10)。
    label = ("他の会社の無料サンプル" if company else "無料サンプル (実文を先に見る)")
    return ('<a style="' + _BAR_A + '" href="/dsh-money-engine/sample.html"'
            ' onclick="' + beacon_js("cta-sample") + ';return true">' + label + "</a>")


def html(company: str = "", count_txt: str = "", hist: bool = False) -> str:
    """頁の末尾に置く注文欄。company を渡すと form に会社名を先に入れた状態で開く。
    hist=True の面 (店) だけ、$25 の履歴一式の中身を manifest の実測で並べる。"""
    u = (url(company) if company else url()).replace("&", "&amp;")
    note = ("開いた注文 form には会社名が既に入っています。" if company
            else "開いた注文 form で会社名と個数を選びます。")
    cnt = (count_txt + "・") if count_txt else ""
    return (BLOCK_OPEN + "<p style='" + _WRAP + "'><a href='" + u + "' style='" + _CSS +
            "' onclick=\"" + beacon_js("order-click") + ";return true\">" +
            _cta_text(company) + "</a><span style='" + _RAW + "'>" + cnt +
            PRICE_LINE.replace("**", "") + "・出典URLつき。" + note +
            ACCOUNT_NOTE + "。</span></p>" +
            "<p style='" + _CARD_WRAP + "'>" + MAIL_NOTE + "　·　" +
            mailto_link(company) + "</p>" + (history_block() if hist else "") + BLOCK_CLOSE)


def bar(company: str = "") -> str:
    """h1 の直下 (最初の1画面) に置く短い注文欄。読まずに買えるようにする。"""
    u = (url(company) if company else url()).replace("&", "&amp;")
    return ("<p style='" + _BAR_WRAP + "'>💴 <a style='" + _BAR_A + "' href='" + u +
            "' onclick=\"" + beacon_js("order-click") + ";return true\">" +
            _cta_text(company) + "</a>　" + PRICE_LINE.replace("**", "") +
            "　·　" + _free_sample(company) + "　·　" + deadline_link(company)
            + "　·　" + ACCOUNT_NOTE + "</p>")


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
    # 同じ頁に古い注文欄が有ったら落としてから差し直す (強制更新)。marker 付きと、
    # marker を入れる前の旧 block (mailto 行が無く、何度再生成しても更新されなかった
    # 実測: mailto を載せる面が 4 / 487 頁) の両方を掃除する。
    # 段落 (</p> まで) を単位に落とす。跨いで消すと隣の文まで消える (実測: data-license の
    # 「今積んでいる観測 3 件」を道連れにして money_check ★ になった)。
    h2 = re.sub(re.escape(BLOCK_OPEN) + r"[\s\S]*?" + re.escape(BLOCK_CLOSE), "", h)
    kept = []
    for para in re.split(r"(</p>)", h2):
        # 落とすのは下端の注文欄 (_WRAP の #e3e7ed) とメール行 (MAIL_NOTE) だけ。
        # 上部欄 (strip) は #fff7e8 なので触らない。実測: 「template=order.yml を含む段落を
        # 全部落とす」だと、行ごとに $5 を置いた締切頁では表ごと消える (2026-10-11)。
        if MAIL_NOTE in para or ("template=order.yml" in para and "#e3e7ed" in para):
            continue
        kept.append(para)
    h2 = "".join(kept)
    if h2 != h:
        h = h2
        changed = True
    # 「order link が有るから挿さない」にすると、行に $5 を置いた頁 (締切頁) で下端の注文欄が
    # 永久に入らなかった (実測 live: mailto 無し)。marker で数える。
    if BLOCK_OPEN not in h:
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
