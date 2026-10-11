"""料金を出す面に『カードで買える口』が実在するかを実測する護り。
既存の check_payment_rail.py はレール自体の開放 (payout 接続) を見張る計器。こちらは面の側。

実測 (2026-10-11): 値段を出している 7 面のどこにもカード決済の link が無かった。
  data-license.html  card=無 crypto=有   ← 料金表を載せている頁これ
  store/index.html   card=無 crypto=有
  sample.html        card=無 crypto=無
  index.html         card=無 (誤検ちに注意: 「三井住友カード」という会社名が表に有る)
日本のお茶の子は Base/Arbitrum/Polygon の ETH を持っていない。送金只能は注文が
入っても入金できない、という意味。order form (GitHub) は注文を受けるだけで入金しない。
link の判定は href の中身だけを見る (本文の語で判定すると会社名に化かされる)。
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent

# 値段を載せている面 = カード口が要る面
PRICED = [
    "index.html", "data-license.html", "sample.html", "question-lineups.html",
    "es-deadlines.html", "store/index.html", "store/mini.html",
]
CARD_HOSTS = ("gumroad.com", "paypal.com", "stripe.com", "buy.stripe.com",
              "lemonsqueezy.com", "ko-fi.com", "pay.me", "bitpay.com")
CRYPTO_RE = re.compile(r"0x[a-fA-F0-9]{40}|送金")
ORDER_RE = re.compile(r"template=order\.yml")
HTML_ATTR = re.compile(r"""(?:href|action)\s*=\s*["']([^"']+)["']""", re.I)


def card_links(h: str) -> list:
    return [u for u in HTML_ATTR.findall(h) if any(k in u for k in CARD_HOSTS)]


def audit(quiet: bool = False) -> list:
    """(rel, カードlink数, 送金有, 注文form有, メールlink数) を返す。"""
    out = []
    for rel in PRICED:
        f = ROOT / rel
        if not f.exists():
            out.append((rel, 0, False, False, 0))
            continue
        h = f.read_text(encoding="utf-8", errors="replace")
        n_mail = len([u for u in HTML_ATTR.findall(h) if u.startswith("mailto:")])
        out.append((rel, len(card_links(h)), bool(CRYPTO_RE.search(h)),
                    bool(ORDER_RE.search(h)), n_mail))
    if not quiet:
        n_card = sum(r[1] for r in out)
        no_card = [r[0] for r in out if r[1] == 0]
        print(f"    支払いの口        : 面の合計 カード link {n_card} 本"
              f" / 注文 form {sum(1 for r in out if r[3])}/{len(out)} 面"
              f" / 送金 {sum(1 for r in out if r[2])} 面"
              f" / メール {sum(1 for r in out if r[4] > 0)}/{len(out)} 面")
        if no_card:
            print(f"      ★ カード口が無い {len(no_card)} 面: {no_card[:4]}")
    return out


def check(quiet: bool = False) -> bool:
    """カード口が有れば最善。無いなら『無い』を頁に書いてあるかを要求する。
    嘘 (カードが有るように見える / 支払いの書かれた面) を通さない。"""
    import buy_block
    rows = audit(quiet)
    no_card, lying, honest, no_mail = [], [], [], []
    for rel, n_card, _crypto, _order, n_mail in rows:
        f = ROOT / rel
        h = f.read_text(encoding="utf-8", errors="replace") if f.exists() else ""
        if n_mail == 0:
            # 2026-10-11 に 3 番目の口として入れた物。実測で締切頁 (一番読まれる面・34 load)
            # から mailto が消えていた (inject が order link を見て差し込みを飛ばしていた)。
            no_mail.append(rel)
        if n_card > 0:
            continue
        no_card.append(rel)
        if buy_block.HONEST in h:
            honest.append(rel)
        else:
            lying.append(rel)
    ok = not lying and not no_mail
    print(f"    カードで買えるか  : "
          + ("OK" if ok else f"★ 支払いを何も書いていない {len(lying)} 面 / メール口の無い {len(no_mail)} 面 (実測)"
             if no_mail else
             ("OK" if not lying else f"★ 支払いを何も書いていない {len(lying)} 面 (実測)"))
          + f" / カード口 {len([r for r in rows if r[1] > 0])} 面"
          + f" / 正直な注記 {len(honest)} 面"
          + f" / メール口 {len([r for r in rows if r[4] > 0])}/{len(rows)} 面")
    if lying:
        print(f"      ★ 例: {lying[:4]}")
    if no_mail:
        print(f"      ★ メール口の無い面: {no_mail[:4]}")
    return ok


if __name__ == "__main__":
    if not check():
        print("★★★ GUARD FAIL: rails — 料金を出す面にカードかメールの口が無い")
        raise SystemExit(1)
    print("  支払いの口 OK")
