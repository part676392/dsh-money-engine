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
import urllib.parse

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


def template_plan_options() -> list:
    """form (.github/ISSUE_TEMPLATE/order.yml) の plan 選択肢。URL prefill は一字一句一致でしか
    入らないので、頁に載せる料金語の正解はここになる。"""
    f = ROOT / ".github" / "ISSUE_TEMPLATE" / "order.yml"
    if not f.exists():
        return []
    t = f.read_text(encoding="utf-8")
    m = re.search(r"id:\s*plan[\s\S]*?options:\s*([\s\S]*?)\n\s*-\s*type:", t)
    if not m:
        return []
    return [o.strip().strip('"\'') for o in re.findall(r"^\s*-\s*(.+?)\s*$", m.group(1), re.M)]


def plan_prefills(quiet: bool = False) -> bool:
    """頁の注文 link が form に存在しないプラン語を prefill していないかの点検。
    実測 (2026-10-11): 既定値は合っていた (990 本) が、メール口の文面だけが『1社ぶん ($5)』で
    form の選択肢『1社だけ試す ($5)』と食い違っていた (客に料金語を二通り見せる)。"""
    import glob as _glob
    import random as _random
    opts = template_plan_options()
    if not opts:
        print("    プラン語の一致    : ★ form の plan 選択肢が読めない")
        return False
    files = [ROOT / f for f in PRICED]
    comp = [pathlib.Path(x) for x in _glob.glob(str(ROOT / "company" / "*.html"))]
    _random.seed(7)
    files += _random.sample(comp, min(24, len(comp)))
    bad, noplan, total, free_ok = [], [], 0, 0
    for f in files:
        if not f.exists():
            continue
        h = f.read_text(encoding="utf-8", errors="replace")
        for u in re.findall(r"""href=["']([^"']*template=order\.yml[^"']*)""", h):
            total += 1
            q = urllib.parse.parse_qs(urllib.parse.urlparse(u.replace("&amp;", "&")).query)
            if "plan" not in q:
                # 自由に用件を書く口 (data-license の注文フォーム link) だけは plan 無しを許す
                if f.name == "data-license.html":
                    free_ok += 1
                    continue
                noplan.append(f.name)
                continue
            v = q["plan"][0]
            if v not in opts:
                bad.append(f"{f.name}: {v!r}")
    ok = not bad and not noplan
    first = (bad + noplan)
    print("    プラン語の一致    : " + ("OK" if ok else "★ " + first[0][:80])
          + f" (link {total:,} 本 / 選択肢 {len(opts)} 個 / 用件自由の口 {free_ok} 本は plan 無しを許す)")
    return ok


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
    plans_ok = plan_prefills(quiet)
    ok = not lying and not no_mail and plans_ok
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
    if not plans_ok:
        print("      ★ form に無いプラン語か、plan の無い link が有る")
    return ok


if __name__ == "__main__":
    if not check():
        print("★★★ GUARD FAIL: rails — 料金を出す面の口 (カード/メール) かプラン語が壊れている")
        raise SystemExit(1)
    print("  支払いの口 OK")
