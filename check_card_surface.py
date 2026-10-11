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
    # メール口の件名も同じ選択肢からしか作らせない (全 html を見る。実測で 11 頁が腐っていた)。
    import glob as _g2
    bad_mail, n_mail = [], 0
    for f in sorted(_g2.glob(str(ROOT / "*.html")) + _g2.glob(str(ROOT / "store" / "*.html"))
                    + _g2.glob(str(ROOT / "company" / "*.html"))):
        h = pathlib.Path(f).read_text(encoding="utf-8", errors="replace")
        # href 単位で取る。`mailto:[^"]*subject=` は貪欲で、同じ頁の最後の link の件名しか
        # 見えず、最初の link を腐らせても ★ が出なかった (制御で実測)。
        for a_ in re.findall(r"""href=["'][^"']*mailto:[^"']*["']""", h):
            m = re.search(r"subject=([^&\"]*)", a_)
            if not m:
                continue
            n_mail += 1
            subj = urllib.parse.unquote(m.group(1))
            if not subj.startswith("注文: "):
                continue                      # data-license の『データ購入の注文』等は自由文
            tier = subj[len("注文: "):].split(" / ")[0]
            if tier not in opts:
                bad_mail.append(f"{pathlib.Path(f).name}: {tier!r}")
                break
    ok = not bad and not noplan and not bad_mail
    first = (bad + noplan + bad_mail)
    print("    プラン語の一致    : " + ("OK" if ok else "★ " + first[0][:80])
          + f" (link {total:,} 本 / 件名 {n_mail:,} 本 / 選択肢 {len(opts)} 個"
          + f" / 用件自由の口 {free_ok} 本は plan 無しを許す)")
    return ok


def provenance_shown(quiet: bool = False) -> bool:
    """出典が『想定質問集』だと面が言っているか + 実測の本数と合っているか。
    実測 (2026-10-11): この種のことを書いていた面は 0 / 7 だった (『実録』等の語も無し)。
    買ってから『これ実録じゃないの？』が起きる前に書く。"""
    import json as _json
    f = ROOT / "data" / "full_bodies.json"
    n_all = n_sh = 0
    if f.exists():
        d = _json.loads(f.read_text(encoding="utf-8"))
        n_all, n_sh = len(d), sum(1 for v in d.values()
                                 if "想定質問" in ((v.get("title") or "") + (v.get("text") or "")))
    missing, wrong, shown = [], [], 0
    for rel in PRICED:
        fp = ROOT / rel
        h = fp.read_text(encoding="utf-8", errors="replace") if fp.exists() else ""
        t = re.sub(r"<[^>]+>", " ", h)
        if "想定質問" not in t or "転載ではありません" not in t:
            missing.append(rel)
            continue
        shown += 1
        m = re.search(r"記事 ([\d,]+) 本。うち ([\d,]+) 本", t)
        if not m:
            wrong.append(f"{rel}: 本数を書いていない")
        elif (int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))) != (n_all, n_sh):
            wrong.append(f"{rel}: {m.group(1)}/{m.group(2)} / 実測 {n_all}/{n_sh}")
    ok = not missing and not wrong and n_all > 0
    first = (missing + wrong)
    print("    出典の性質        : " + ("OK" if ok else "★ " + (first[0] if first else "実測が取れない")[:76])
          + f" ({shown}/{len(PRICED)} 面が『想定質問』と明記 / 実測 {n_all} 本中 {n_sh} 本)")
    return ok


def history_honest(quiet: bool = False) -> bool:
    """$25 の中身を実数で出している面と、manifest の実測が一致しているかの点検。
    実測 (2026-10-11): 中身を出していたのは 2 面だけで、質問実文を出す面と同じ数が抜けていた。"""
    import csv as _csv
    man = {}
    mf = ROOT / "exports" / "manifest.csv"
    if mf.exists():
        with open(mf, encoding="utf_8_sig") as fh:
            for r in _csv.DictReader(fh):
                man[r.get("file", "")] = int(r.get("rows") or 0)
    if not man:
        print("    $25 の中身        : ★ manifest が読めない")
        return False
    need = {k: v for k, v in man.items()
            if k in ("history_timeseries.csv", "es_deadlines_history.csv", "source_liveness.csv")}
    missing, stale, shown = [], [], 0
    for rel in PRICED:
        f = ROOT / rel
        h = f.read_text(encoding="utf-8", errors="replace") if f.exists() else ""
        i = h.find("歴史スナップショット一式 ($25) の中身")
        if i < 0:
            missing.append(rel)
            continue
        shown += 1
        seg = re.sub(r"<[^>]+>", " ", h[i:i + 700])
        for fname, rows in need.items():
            m = re.search(re.escape(fname) + r"\s*\((\d+) 行\)", seg)
            if not m:
                stale.append(f"{rel}: {fname} の行数が無い")
            elif int(m.group(1)) != rows:
                stale.append(f"{rel}: {fname} {m.group(1)} 行 / manifest {rows} 行")
    ok = not missing and not stale
    first = (missing + stale)
    print("    $25 の中身        : " + ("OK" if ok else "★ " + first[0][:76])
          + f" ({shown}/{len(PRICED)} 面が実数を出し、manifest {len(need)} ファイルと一致"
          + f" / 全站 {len(list((ROOT).glob('*.html')))} 頁に展開)")
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
    hist_ok = history_honest(quiet)
    prov_ok = provenance_shown(quiet)
    ok = not lying and not no_mail and plans_ok and hist_ok and prov_ok
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
    if not hist_ok:
        print("      ★ $25 の中身を実数で出していない / manifest と違う面が有る")
    if not prov_ok:
        print("      ★ 出典が想定質問集であることを書いていない / 本数が実測と違う")
    return ok


if __name__ == "__main__":
    if not check():
        print("★★★ GUARD FAIL: rails — 料金を出す面の口 (カード/メール) かプラン語が壊れている")
        raise SystemExit(1)
    print("  支払いの口 OK")
