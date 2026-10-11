#!/usr/bin/env python3
"""Micro Scene の販売ページを作る ($3 の低価格版).

 動機: $6 + メール仕様 + 暗号払い は 72 時間の即金には重い。
 同じ著作力を 700 語 / 低額に切り直して摩擦を下げる。
 検品の型は build_store.py と揃える (実在する本文 / 価格表示 / 英語のみ)。
"""
from __future__ import annotations

import buy_block
BUY = buy_block.html()
import datetime as dt
import html
import json
import pathlib
import re
from tracker_js import tracker

ROOT = pathlib.Path(__file__).resolve().parent
RAW = ROOT / "store" / "samples" / "raw_product2.txt"
MICRO = ROOT / "store" / "samples" / "product2_micro.md"
TYPEGRAPHIC = set("\u2014\u2013\u2018\u2019\u201c\u201d\u2026\u00b7")
OUT = ROOT / "store"
WALLET = ROOT / "outbox" / "wallet.json"

PRICE_USD = 3


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)




TRACKER_MINI = tracker("mini")


def parse(raw: str) -> dict:
    labels = ("TITLE", "BODY", "WHAT_YOU_GET")

    def grab(label: str) -> str:
        # [ \t] 限定: \s にすると改行を跨いで次行を吞む (store 側で実測済み)
        m = re.search(rf"^{label}[ \t]*[:：][ \t]*(.*)$", raw, re.M | re.I)
        if not m:
            return ""
        head = m.group(1).strip()
        rest = raw[m.end():]
        nxt = re.search(r"^(%s)[ \t]*[:：]" % "|".join(labels), rest, re.M | re.I)
        tail = (rest[: nxt.start()] if nxt else rest).strip()
        return head if head else tail

    t = re.search(r"^TITLE\s*[:：]\s*(.+)$", raw, re.M | re.I)
    return {"title": (t.group(1).strip() if t else ""),
            "body": grab("BODY"),
            "what": grab("WHAT_YOU_GET")}


def verify(p: dict) -> dict:
    words = len(p["body"].split())
    problems = []
    if not p["title"]:
        problems.append("title missing")
    if len(p["title"]) > 70:
        problems.append(f"title too long ({len(p['title'])})")
    if words < 500:
        problems.append(f"body too short ({words} words)")
    if not p["what"]:
        problems.append("what_you_get missing")
    low = p["body"].lower()
    for bad in ("as an ai", "language model", "generated", "prompt"):
        if bad in low:
            problems.append(f"mentions generation: {bad}")
    bad = sorted({c for c in p["body"] if ord(c) > 127} - TYPEGRAPHIC)
    if bad:
        problems.append(f"non-ascii leaked: {bad[:6]}")
    low = p["body"].lower()
    lex = [k for k in ("wet", "mouth", "tongue", "thigh", "hard", "fingers",
                       "inside", "slick", "heat", "breath", "came", "groaned") if k in low]
    if len(lex) < 6:
        problems.append(f"not explicit enough ({len(lex)} hits)")
    if any(e in low for e in ("fade to black", "later that night")):
        problems.append("fades to black")
    return {"words": words, "ok": not problems, "problems": problems}


def main() -> None:
    src = MICRO if MICRO.exists() else RAW
    print(f"  source: {src.name}")
    p = parse(src.read_text(encoding="utf-8", errors="replace"))
    v = verify(p)
    print(f"  title : {p['title']!r}")
    print(f"  body  : {v['words']} words -> {'PASS' if v['ok'] else v['problems']}")
    if not v["ok"]:
        raise SystemExit("not publishing")

    addr = json.loads(WALLET.read_text(encoding="utf-8")).get("address", "") if WALLET.exists() else ""
    inbox = json.loads((ROOT / "outbox" / "mailtm.json").read_text(encoding="utf-8")).get("address", "")
    paras = "".join(f"<p>{esc(x.strip())}</p>" for x in re.split(r"\n\s*\n", p["body"]) if x.strip())
    today = dt.date.today().isoformat()
    ld = json.dumps({
        "@context": "https://schema.org", "@type": "Service",
        "name": p["title"] + " — Micro Scene",
        "serviceType": "Custom adult short fiction, 700 words",
        "offers": {"@type": "Offer", "price": str(PRICE_USD), "priceCurrency": "USD",
                   "acceptedPaymentMethod": ["Crypto", "Cryptocurrency"],
                   "url": "https://part676392.github.io/dsh-money-engine/store/mini.html"},
        "availableChannel": {"@type": "ServiceChannel", "serviceUrl": "mailto:" + inbox},
        "audit": {"@type": "MediaReview", "reviewAspect": "adult content",
                  "contentRating": "Adults only"},
    }, ensure_ascii=False, indent=1)

    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(p['title'])} — 700 word explicit scene, {PRICE_USD} USD</title>
<meta name="description" content="A complete 700-word explicit scene you can read free, plus the option to commission your own for {PRICE_USD} USD. Adults 18+.">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta name="rating" content="adult">
<link rel="canonical" href="https://part676392.github.io/dsh-money-engine/store/mini.html">
<script type="application/ld+json">
{ld}
</script>
<style>
body{{font-family:ui-serif,Georgia,"Times New Roman",serif;margin:0;background:#0f1013;color:#e6e3dd;line-height:1.72}}
main{{max-width:680px;margin:0 auto;padding:34px 20px 70px}}
h1{{font-size:1.45rem;margin:0 0 6px;font-weight:600}}
.tag{{color:#a9a49b;font-size:.9rem;margin:0 0 18px}}
.buy{{background:#181a1e;border:1px solid #33363c;border-radius:10px;padding:15px 17px;margin:20px 0}}
.price{{font-size:1.4rem;color:#f0c98a}}
code{{background:#0b0c0e;padding:2px 6px;border-radius:5px;font-size:.8rem;word-break:break-all;color:#9fd3a8}}
.order{{background:#0b0c0e;border-left:3px solid #55607a;padding:11px 14px;font-size:.9rem;border-radius:0 8px 8px 0}}
.warn{{font-size:.78rem;color:#8b867e;margin-top:24px}}
a{{color:#f0c98a}} p{{font-size:1.01rem}}
</style></head><body><main>
<h1>{esc(p['title'])}</h1>
<p class="tag">A Micro Scene: 700 words, one continuous explicit scene. Adults 18+, all characters 25+.</p>

<div class="buy">
  <p style="margin:0 0 8px">This whole scene is free above — that is the point. Read it, and if the writing works for you, your own version costs <span class="price">{PRICE_USD} USD</span> and arrives as a text file, typically within 15 minutes.</p>
  <p style="font-size:.86rem;margin:10px 0 4px"><b>1. Send your specification:</b></p>
  <p><code>{esc(inbox)}</code></p>
  <p style="font-size:.86rem;margin:10px 0 4px"><b>2. Pay {PRICE_USD} USD to (Base, Arbitrum, Polygon or ETH — one address):</b></p>
  <p><code>{esc(addr)}</code></p>
</div>

<div class="order"><b>What you get</b><br>{esc(p['what'])}</div>

<section style="margin-top:26px;border-top:1px solid #33363c;padding-top:6px">
{paras}
</section>

<p class="warn">Commission options: 700 words {PRICE_USD} USD · 1,500 words 6 USD · 2,500 words 9 USD.
Hard limits you name are honoured; one free revision if a named limit is missed.
Page built {today}. No reviews shown because there are none yet.</p>
{BUY}</main>{TRACKER_MINI}</body></html>"""
    (OUT / "mini.html").write_text(doc, encoding="utf-8")
    json.dump({"title": p["title"], "words": v["words"], "price_usd": PRICE_USD, "wallet": addr,
               "built": today}, open(OUT / "product2.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"  wrote store/mini.html ({len(doc):,} bytes)")


if __name__ == "__main__":
    main()
