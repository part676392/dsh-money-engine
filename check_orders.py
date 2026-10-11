#!/usr/bin/env python3
"""匿名受信箱を受注口として無人で見る.

 mail.tm は受信できる。つまり API が読める。
 買主は s8l...@maxxspace.com へ仕様を送り、俺はここで拾って配送する。
 バックエンドもフォームも人の協力も要らない。
 前回の自分の失敗: token を保存して使い回した。mail.tm の token は
 1 時間で失効するので、毎回 password から取り直す。
"""
from __future__ import annotations

import base64
import json
import re
import sys
import pathlib
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent
CRED = ROOT / "outbox" / "mailtm.json"
HIST = ROOT / "data" / "orders"
B = "https://api.mail.tm"


def curl(args: list, timeout: int = 25) -> tuple:
    try:
        r = subprocess.run(["curl", "-s", "--max-time", str(timeout)] + args,
                           capture_output=True, text=True, timeout=timeout + 6)
        return r.stdout, None
    except Exception as e:  # noqa: BLE001
        return "", str(e)[:80]


def token(addr: str, pw: str) -> str:
    body = json.dumps({"address": addr, "password": pw})
    out, err = curl(["-X", "POST", f"{B}/token", "-H", "Content-Type: application/json", "-d", body])
    try:
        return json.loads(out).get("token", "")
    except Exception:  # noqa: BLE001
        print(f"  token failed: {err or out[:80]}")
        return ""


def messages(tok: str) -> list:
    out, err = curl(["-H", f"Authorization: Bearer {tok}", f"{B}/messages"])
    try:
        return json.loads(out).get("hydra:member", [])
    except Exception:  # noqa: BLE001
        print(f"  inbox read failed: {err or out[:80]}")
        return []


def message_detail(tok: str, mid: str) -> dict:
    out, _ = curl(["-H", f"Authorization: Bearer {tok}", f"{B}/messages/{mid}"])
    try:
        return json.loads(out)
    except Exception:  # noqa: BLE001
        return {}


def seen_ids() -> set:
    f = HIST / "seen.json"
    if f.exists():
        try:
            return set(json.loads(f.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            return set()
    return set()


TIERS = {700: 3, 1500: 6, 2500: 9}
SPEC_KEYS = {
    "characters": ("character", "characters", "protagonist", "二人", "主人公"),
    "setting": ("setting", "scene", "place", "laundromat", "office", "舞台"),
    "tone": ("tone", "mood", "steamy", "romantic", "rough", " tender", "雰囲気"),
    "limits": ("limit", "hard limit", "no ", "don't", "avoid", "禁止", "苦手"),
    "length": ("words", "word count", "語", "文字"),
}
PAY_WORDS = ("paid", "pay ", "payment", "i pay", "sending", "sent", "tx", "tx hash",
             "transfer", "usdc", "eth", "base",
             "送金", "支払った", "支払済み", "振り込み")
ORDER_WORDS = ("order", "commission", "i want", "i'd like", "please write", "request",
               "依頼", "注文", "お願い", "頼みたい")
WRITING_WORDS = ("words", "word count", "scene", "story", "piece", "draft", "fiction",
                 "manuscript", "writing", "written", "write", "ever", "ering",
                 "原稿", "執筆", "話", "シーン", "文字")


def parse_order(text: str) -> dict:
    """受注メールらしき本文から取れる物だけ取る.

    取れない欄は空で出す。勝手に埋めないのが約束。
    """
    t = " ".join((text or "").split())
    low = t.lower()
    words = [int(w) for w in re.findall(r"(\d{3,5})\s*(?:words|word|語|文字)", low)]
    tier = None
    # まずasciiな語数指定を厳密に拾う。外れたら一番近い段に寄せるが、
    # 寄せたことは zone に残す (勝手に確定扱いしない)。
    tier_zone = "exact"
    for w in sorted(words, reverse=True):
        if w in TIERS:
            tier = w
            break
    if tier is None and words:
        tier = min(TIERS, key=lambda k: abs(k - words[0]))
        tier_zone = "nearest"
    price = None
    pm = re.search(r"(?:usd|\$|ドル)\s*([0-9]+(?:\.[0-9]+)?)", low)
    if pm:
        price = float(pm.group(1))
    elif tier:
        price = TIERS[tier]
    spec = {k: True for k, keys in SPEC_KEYS.items() if any(x in low for x in keys)}
    pay = any(w in low for w in PAY_WORDS)
    order_word = any(w in low for w in ORDER_WORDS)
    # 意図語だけだと "buy cheap followers" の様な販促が全部受注になる (self-test で実測)。
    # 執筆物の気配を重ねて要求する。
    writing = any(w in low for w in WRITING_WORDS)
    order = (order_word and writing) or pay or (tier is not None and tier_zone == "exact")
    tx = re.search(r"\b0x[0-9a-f]{16,}\b", low)
    return {
        "looks_like_order": order or pay or bool(tier),
        "requested_words": tier,
        "tier_zone": tier_zone,
        "price_usd": price,
        "spec_sections": sorted(spec.keys()),
        "payment_claimed": pay,
        "tx_hash": (tx.group(0) if tx else None),
        "chars": len(t),
    }


FIXTURES = [
    {"name": "本物の受注 (英語)",
     "text": ("Hi, I'd like to order 1500 words. Characters: two rivals stuck in a "
              "laundromat. Setting: 2am, rain. Tone: slow burn, steamy. Hard limits: no "
              "minors, no non-con. I will pay 6 USD to your address."),
     "expect": {"looks_like_order": True, "requested_words": 1500, "price_usd": 6.0,
                "payment_claimed": True}},
    {"name": "支払い報告 (tx あり)",
     "text": ("Paid. Sent USDC on Base, tx 0x9f2b4c7de1a3f58b0c47e2d16a8593f0b1c7d4e2. "
              "Looking forward to the 700 words scene."),
     "expect": {"looks_like_order": True, "requested_words": 700, "payment_claimed": True}},
    {"name": "質問だけで注文ではない",
     "text": "Do you take requests? What formats can you deliver in?",
     "expect": {"looks_like_order": False, "payment_claimed": False}},
    {"name": "スパム (暗号通貨の便乗)",
     "text": "HOT: buy cheap followers now, click here limited offer today only",
     "expect": {"looks_like_order": False}},
]


def selftest() -> int:
    ok = 0
    print("  parser self-test (実メール不要の巡回):")
    for fx in FIXTURES:
        got = parse_order(fx["text"])
        bad = {k: (v, got.get(k)) for k, v in fx["expect"].items() if got.get(k) != v}
        flag = "✓" if not bad else "✗"
        if not bad:
            ok += 1
        line = (f"    {flag} {fx['name']:22s} order={got['looks_like_order']} "
                f"words={got['requested_words']} price={got['price_usd']} "
                f"spec={','.join(got['spec_sections']) or '-'} pay={got['payment_claimed']}")
        print(line + (f"   ★ 不一致 {bad}" if bad else ""))
    print(f"  parser self-test: {ok}/{len(FIXTURES)} PASS")
    return 0 if ok == len(FIXTURES) else 1


def issue_orders() -> dict:
    """GitHub issue 受注口。受信箱は受信専用で外送信できないので、
    注文を公開の issue で受けて、納品URLをそこに返す (実装: .github/ISSUE_TEMPLATE/order.yml)。
    ラベル 注文 を開いている間だけ注文として数える。rehearsal 付きは練習で除外。"""
    q = "repos/part676392/dsh-money-engine/issues?state=open&labels=%E6%B3%A8%E6%96%87&per_page=50"
    out, err = curl(["-H", "Accept: application/vnd.github+json", q]) if False else ("", "")
    try:
        r = subprocess.run(["gh", "api", q], capture_output=True, text=True, timeout=45)
        arr = json.loads(r.stdout) if r.returncode == 0 else []
    except Exception as e:  # noqa: BLE001
        print(f"  issue orders: 取得失敗 {str(e)[:50]}")
        return {"open": 0, "real": 0, "rehearsal": 0, "items": []}
    items = []
    for it in arr:
        if it.get("pull_request"):
            continue
        labs = [l.get("name", "") for l in (it.get("labels") or [])]
        items.append({"number": it.get("number"), "title": (it.get("title") or "")[:80],
                      "url": it.get("html_url"), "rehearsal": "rehearsal" in labs,
                      "created": (it.get("created_at") or "")[:10]})
    real = [x for x in items if not x["rehearsal"]]
    print(f"  issue orders      : open {len(items)}  実注文 {len(real)}  練習 {len(items)-len(real)}"
          + ("  " + ", ".join("#" + str(x["number"]) for x in real[:4]) if real else ""))
    # 台帳に上げる (同じ issue を二重に積まない)
    dpath = ROOT / "data" / "deliveries.json"
    led = {}
    if dpath.exists():
        try:
            led = json.loads(dpath.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            led = {}
    # 不成立 (送金なし) のまま受領中が台帳に残ると実注文が水増しされる (実測: closed 直後も
    # labels 付き query が #2 を返し続けた = GitHub の index 遅延が数秒)。次の巡回で落ちる。
    open_keys = {f"GH-{x['number']}" for x in real}
    for k, v in led.items():
        if k.startswith("GH-") and k not in open_keys and "納品" not in str(v.get("status", "")):
            v["status"] = "不成立 (送金なし)"
            print(f"  台帳 {k}: 不成立として落とした")
    for x in real:
        k = f"GH-{x['number']}"
        if k not in led:
            led[k] = {"kind": "issue", "status": "受領 (送金待ち)", "url": x["url"],
                      "title": x["title"], "received_at": x["created"]}
            print(f"  ★ 受領 #{x['number']} を台帳に追加 (実数は送金確認後)")
    if led:
        dpath.write_text(json.dumps(led, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"open": len(items), "real": len(real), "rehearsal": len(items) - len(real),
            "items": items}


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if not CRED.exists():
        print("  no mailtm.json")
        return 0
    c = json.loads(CRED.read_text(encoding="utf-8"))
    addr, pw = c.get("address", ""), c.get("password", "")
    HIST.mkdir(parents=True, exist_ok=True)

    tok = token(addr, pw)
    if not tok:
        print("  could not get token (mailbox may have expired; recreate with mailtm setup)")
        return 0
    msgs = messages(tok)
    seen = seen_ids()
    fresh = [m for m in msgs if m.get("id") not in seen]
    print(f"  inbox: {len(msgs)} message(s), unseen: {len(fresh)}")

    orders = []
    for m in fresh[:6]:
        d = message_detail(tok, m["id"])
        text = (d.get("text") or "").strip()
        html_body = d.get("html") or []
        if not text and html_body:
            raw = html_body[0] if isinstance(html_body, list) else str(html_body)
            try:
                raw = base64.b64decode(raw).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                pass
            import re as _re
            text = _re.sub(r"<[^>]+>", " ", raw)
        parsed = parse_order(text)
        rec = {
            "id": m.get("id"),
            "from": (m.get("from") or {}).get("address"),
            "subject": m.get("subject"),
            "received": m.get("createdAt"),
            "intro": " ".join(text.split())[:280],
            **parsed,
        }
        # 本文が空 / 受注の気配が無いものは受注として数えない (ダッシュボード汚染防止)。
        if parsed["looks_like_order"] or text.strip():
            orders.append(rec)
        if parsed["looks_like_order"]:
            print(f"  ★ ORDER from {rec['from']}  «{rec['subject']}»")
            print(f"          words={parsed['requested_words']} ({parsed['tier_zone']}) "
                  f"price=${parsed['price_usd']} pay={parsed['payment_claimed']} "
                  f"spec={','.join(parsed['spec_sections']) or '-'}")
            print(f"          {rec['intro'][:150]}")

    seen |= {m["id"] for m in msgs}
    (HIST / "seen.json").write_text(json.dumps(sorted(seen)), encoding="utf-8")
    if orders:
        with open(HIST / "orders.jsonl", "a", encoding="utf-8") as f:
            for o in orders:
                f.write(json.dumps(o, ensure_ascii=False) + "\n")
    (HIST / "latest.json").write_text(json.dumps(
        {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "total": len(msgs),
         "unseen": len(fresh), "orders": orders}, ensure_ascii=False, indent=1), encoding="utf-8")
    iss = issue_orders()
    d = json.loads((HIST / "latest.json").read_text(encoding="utf-8"))
    d["github_issues"] = iss
    (HIST / "latest.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    if not fresh and not iss["real"]:
        print("  no new orders yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
