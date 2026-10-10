#!/usr/bin/env python3
"""納品物 (deliveries/*.md) を頁にして台帳に積む.

 背景: 受信箱は受信専用 (mail.tm は POST /messages=405) なので、注文が来ても
 作法として外にメールを投げられない。納品は公開URL。その道を、本番で一度
 通しておく (練習 = rehearsal。架空の受注をよそおって出さない)。

 語数と露出語のチェックは code が測る。手で書いた数をそのまま信じない。
"""
from __future__ import annotations

import html
import json
import pathlib
import re
import time

ROOT = pathlib.Path(__file__).resolve().parent
BASE = "https://part676392.github.io/dsh-money-engine"
DIR = ROOT / "deliveries"
LEDGER = ROOT / "data" / "deliveries.json"

# money_check.py の Fiction 側と同じ基準 (露出語の語彙)。
LEXICON = ("naked", "nude", "bare", "breast", "chest", "skin", "thigh", "hip", "waist",
           "mouth", "kiss", "kissed", "tongue", "groan", "arch", "arched", "shiver",
           "touch", "touched", "hand", "hands", "breath", "breathe", "muscle", "body")


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def md_to_html(md: str) -> tuple:
    """軽量変換: 見出しと段落と斜体だけ。全文を escape してから組み立てる。"""
    paras, title = [], "納品物"
    for block in re.split(r"\n\s*\n", md.strip()):
        b = block.strip()
        if not b or b.startswith("SPEC:"):
            continue
        if b.startswith("# "):
            title = b[2:].strip()
            continue
        t = esc(b).replace("\n", " ")
        t = re.sub(r"\*(.+?)\*", r"<i>\1</i>", t)
        paras.append(f"<p>{t}</p>")
    return title, "\n".join(paras)


def main() -> int:
    files = sorted(DIR.glob("*.md"))
    if not files:
        print("  deliveries/*.md が無い: 納品物はまだ")
        return 0
    ledger = {}
    if LEDGER.exists():
        try:
            ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
        except Exception:
            ledger = {}
    made = []
    for f in files:
        md = f.read_text(encoding="utf-8")
        spec = ""
        m = re.search(r"^SPEC:\s*(.+)$", md, re.M)
        if m:
            spec = m.group(1).strip()
        title, body = md_to_html(md)
        plain = re.sub(r"<[^>]+>", " ", body)
        words = len([w for w in re.findall(r"[A-Za-z][A-Za-z'\-]+", plain)])
        low = plain.lower()
        lex = sum(low.count(k) for k in LEXICON)
        oid = f"REHEARSAL-{f.stem.split('-')[-1]}"
        url = f"{BASE}/deliveries/{f.stem}.html"
        ld = json.dumps({
            "@context": "https://schema.org", "@type": "CreativeWork",
            "name": title, "inLanguage": "en",
            "wordCount": words, "genre": "explicit contemporary romance",
            "description": (spec or title)[:250],
            "url": url, "license": "https://creativecommons.org/licenses/by/4.0/",
            "creator": {"@type": "Organization", "name": "dsh-money-engine"},
            "datePublished": time.strftime("%Y-%m-%d"),
        }, ensure_ascii=False, indent=1)
        doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} — 納品物 ({words} words) | dsh-money-engine</title>
<meta name="description" content="{esc((spec or title)[:150])} — {words} words, delivered as a public URL.">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{url}">
<script type="application/ld+json">
{ld}
</script>
<style>
body{{font-family:Georgia,"Hiragino Mincho ProN",serif;margin:0;background:#f8f6f1;color:#1d1c1a;line-height:1.75}}
main{{max-width:660px;margin:0 auto;padding:34px 18px 80px}}
h1{{font-size:1.35rem;margin:0 0 4px}}
.spec{{font-size:.83rem;color:#6d675e;border-bottom:1px solid #e2dccf;padding-bottom:12px;margin:0 0 22px}}
p{{margin:0 0 15px}}
.met{{font-size:.79rem;color:#6d675e;border-top:1px solid #e2dccf;padding-top:14px;margin-top:28px}}
a{{color:#7a5230}}
</style></head><main>
<h1>{esc(title)}</h1>
<p class="spec"><b>Spec</b>: {esc(spec or "—")} ／ <b>{words} words</b> ／ delivered as a public URL (this mailbox receives only)</p>
{body}
<p class="met">これは <b>練習の納品</b> (rehearsal) です — 実際にこの管線が物を-create できることを示すため、
自分の受付番号で通したもの。誰かの注文をよそおってはありません。
　測定: {words} words（code が数えた値）／ 露出語 {lex} 語彙ヒット（基準 6 以上）
　文は自作なので CC BY 4.0 で公開します。
　<a href="{BASE}/deliveries.html">納品一覧</a> ／ <a href="{BASE}/store/">注文</a></p>
</main></body></html>"""
        (DIR / f"{f.stem}.html").write_text(doc, encoding="utf-8")
        ledger[oid] = {"kind": "rehearsal", "status": "納品済み（練習）", "url": url,
                       "words": words, "lexicon_hits": lex, "spec": spec,
                       "received": "self", "delivered_at": ledger.get(oid, {}).get("delivered_at")
                       or time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                       "requested_words": (int(re.search(r"(\d{3,4})", spec).group(1))
                                           if re.search(r"(\d{3,4})", spec) else words)}
        made.append((f.stem, words, lex))
    LEDGER.parent.mkdir(exist_ok=True)
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")
    for stem, w, lex in made:
        flag = "OK" if lex >= 6 else "★ 露出語不足"
        print(f"  {stem}: {w} words  露出語ヒット={lex}  {flag}")
    print(f"  台帳 {LEDGER.name}: {len(ledger)} 件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
