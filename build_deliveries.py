#!/usr/bin/env python3
"""納品一覧 (deliveries.html) をつくる.

 背景: 受信箱は受信専用 (mail.tm は password 付きアカウントでも
 POST /messages = 405 を 2026-10-11 に再確認)。だから注文者にメールで
 返事ができない。約束した納品形は「公開URL」。なのにその一覧の頁が
 無かった (git ls-files で 0 件)。約束した物を実在させる。

 受注0件のうちは空状態を正直に出す。嘘の受注を並べない。
"""
from __future__ import annotations

from tracker_js import tracker
import buy_block
BUY = buy_block.html()
import html
import json
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parent
BASE = "https://part676392.github.io/dsh-money-engine"
OUT = ROOT / "deliveries.html"
DATA = ROOT / "data"
LEDGER = DATA / "deliveries.json"


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def load(p: pathlib.Path, default):
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def collect_orders() -> list:
    """latest と日付付きの両方から集約 (id で重複除去、新しい方を採用)。"""
    got = {}
    files = [DATA / "orders" / "latest.json"] + sorted((DATA / "orders").glob("20*.json"))
    for f in files:
        d = load(f, {})
        for o in (d.get("orders") or []):
            k = str(o.get("id") or o.get("received") or "")
            if k:
                got[k] = o
    return sorted(got.values(), key=lambda o: str(o.get("received", "")), reverse=True)


def main(fixture: bool = False) -> int:
    orders = collect_orders()
    ledger = load(LEDGER, {})

    if fixture:
        # 記入状態のレンダリング検証用。public には出さない (main の --fixture は
        # /tmp へ書き出すときだけ true)。
        orders = [{
            "id": "FIXTURE-01", "from": "buyer@example.com",
            "subject": "order 1500 words", "received": "2026-10-11T06:00:00+09:00",
            "requested_words": 1500, "price_usd": 6.0, "payment_claimed": True,
            "tx_hash": "0xabc123def4567890ab", "looks_like_order": True, "chars": 412,
        }]
        ledger = {"FIXTURE-01": {"status": "delivered",
                                 "url": f"{BASE}/deliveries/FIXTURE-01.html",
                                 "delivered_at": "2026-10-11T06:04:00+09:00",
                                 "words": 1512}}

    # 受信箱が受信専用なので練習の納品は「受注」を通らない。台帳に先に積んだ物を
    # ここでも同じ表に出す (kind で練習だと分かる表記にする)。
    seen_ids = {str(o.get("id") or "") for o in orders}
    for oid, st in ledger.items():
        if oid in seen_ids:
            continue
        orders.append({
            "id": oid, "from": st.get("kind", "rehearsal"), "subject": st.get("spec", ""),
            "received": st.get("delivered_at", "—"), "requested_words": st.get("requested_words"),
            "price_usd": None, "payment_claimed": False, "chars": 0,
        })

    rows = []
    items = []
    for o in orders:
        oid = str(o.get("id") or "—")
        st = ledger.get(oid, {})
        state = st.get("status") or "受注済み・作成中"
        link = (f'<a href="{esc(st.get("url"))}">納品物</a>' if st.get("url") else "—")
        words = o.get("requested_words") or "指定なし"
        price = o.get("price_usd")
        pay = "報告あり" if o.get("payment_claimed") else "未確認"
        if st.get("kind") == "rehearsal":
            pay = "練習 (自分の受付番号で通した)"
        rows.append(
            f"<tr><td><code>{esc(oid[:16])}</code></td>"
            f"<td>{esc(o.get('received','—'))}</td>"
            f"<td>{esc(words)} 語</td>"
            f"<td>{('$' + esc(price)) if price else '—'}</td>"
            f"<td>{esc(pay)}</td><td>{esc(state)}</td><td>{link}</td></tr>")
        items.append({"@type": "ListItem", "position": len(items) + 1,
                      "item": {"@type": "Dataset",
                               "name": f"注文 {oid[:10]} ({words} 語)",
                               "description": f"受付 {o.get('received','—')} / 納品状態 {state}"}})

    body = f"""<table><thead><tr><th>注文番号</th><th>受付</th><th>依頼</th><th>料金</th>
<th>送金</th><th>納品状態</th><th>納品物</th></tr></thead><tbody>
{chr(10).join(rows) if rows else '<tr><td colspan="7">受注はまだ 0 件です。届いたらここに載ります。</td></tr>'}
</tbody></table>"""

    ld = json.dumps({
        "@context": "https://schema.org", "@type": "ItemPage",
        "name": "納品一覧",
        "mainEntity": {"@type": "ItemList",
                       "name": "カスタム抽出と_scene_の納品記録",
                       "numberOfItems": len(items),
                       "itemListElement": items or [{"@type": "ListItem", "position": 1,
                                                     "item": {"@type": "Dataset",
                                                              "name": "受注はまだ0件",
                                                              "description": "届き方の実例をここに積む"}}]},
    }, ensure_ascii=False, indent=1)

    doc = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>納品一覧 — 注文がどこまで進んだか | 目録</title>
<meta name="description" content="受注ごとの納品状態と納品URL。受信箱は受信専用なので納物は公開URLで渡す。その記録をここに積む。">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{BASE}/deliveries.html">
<script type="application/ld+json">
{ld}
</script>
<style>
body{{font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif;margin:0;background:#f6f5f2;color:#1d1c1a;line-height:1.65}}
main{{max-width:920px;margin:0 auto;padding:30px 16px 70px}}
h1{{font-size:1.3rem;margin:0 0 6px}} .sub{{color:#6d675e;font-size:.87rem;margin:0 0 16px}}
table{{width:100%;border-collapse:collapse;font-size:.86rem}}
th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid #ece7de;vertical-align:top}}
th{{background:#efeee9}} code{{background:#efece6;padding:1px 5px;border-radius:4px}}
.why{{background:#fff6e8;border:1px solid #e7cf9f;border-radius:8px;padding:12px 15px;font-size:.86rem;margin:16px 0}}
a{{color:#7a5230}} .note{{font-size:.8rem;color:#6d675e;margin-top:22px}}
.now{{background:#fff;border:1px solid #e6e1d8;border-radius:8px;padding:11px 14px;font-size:.86rem;margin:14px 0}}
</style></head><body><main>
<h1>納品一覧</h1>
<p class="sub">注文ごとに、どこまで進んだかと納品物のURLをここに積みます。</p>

<div class="now"><b>いま</b>: 受注 {len(orders)} 件 ／ 納品済み {sum(1 for v in ledger.values() if 'delivered' in str(v.get('status','')).lower() or '納品済み' in str(v.get('status','')))} 件</div>

{body}

<div class="why"><b>なぜメールで送らないか</b>: ここの受信箱は受信だけで、こちらからメールを送れません
（使い捨てメールの API が送信を許可しないのを再確認済み）。だから納品は<b>公開URL</b>で渡して、
その記録をこの頁に残します。注文番号を受信時にこちらで控えるので、 Ordering 時は
「何語を頼んだか」だけ書けば足ります。</div>

<p class="note">更新: {time.strftime('%Y-%m-%d %H:%M JST')}（毎日 06:10 / 19:40 に自動再生成）
　注文のしかた: <a href="data-license.html">データ資産の購入</a> ／
　<a href="store/">カスタム小説</a> ／ <a href="sample.html">納品物見本</a> ／ <a href="./">目録へ</a></p>
{tracker("deliveries")}{BUY}</main></body></html>"""
    dest = pathlib.Path("/tmp/deliveries_fixture.html") if fixture else OUT
    dest.write_text(doc, encoding="utf-8")
    print(f"  wrote {dest.name} ({len(doc):,} chars)")
    print(f"  受注={len(orders)} 納品済み={sum(1 for v in ledger.values() if 'delivered' in str(v.get('status','')).lower() or '納品済み' in str(v.get('status','')))} "
          f"台帳={len(ledger)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(fixture="--fixture" in __import__("sys").argv))
