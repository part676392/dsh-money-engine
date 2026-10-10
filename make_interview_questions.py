#!/usr/bin/env python3
"""収録記事から「面接で実際に投げられた質問」の実文だけを集める.

 動機: `〇〇 面接 質問` は転職検索で一番意図の強い語。なのに目録には
 件数と価格しかなかった。太い本文 (harvest_full.py) が取れるようになったので、
 質問の実文を企業別に集める。

 取り方:
   1. 文中の「…」で囲まれ ？ で終わる断片を **質問の実文** として優先採用
   2. 囲みが無い場合は ？ で終わる文を採る
   3. 引用元記事 (表題・URL・価格) を必ず添える。勝手に要約しない。

 出さないもの: 一般的な助言文 («〜と答えましょう») は質問として数えない。
"""
from __future__ import annotations

import collections
import html
import json
import pathlib
import re
import time

ROOT = pathlib.Path(__file__).resolve().parent
FULL = ROOT / "data" / "full_bodies.json"
CORPUS = ROOT / "data" / "corpus_full.json"
SNAP = ROOT / "data" / "snapshot-latest.json"
OUT_JSON = ROOT / "data" / "interview_questions.json"
OUT_HTML = ROOT / "interview-questions.html"
BASE = "https://part676392.github.io/dsh-money-engine"

SENT = re.compile(r"(?<=[。！？])\s*")
QUOTED = re.compile(r"[「“]([^」”]{6,140}?[？?])\s*[」”]")
TAG = re.compile(r"<[^>]+>")
ADVICE = re.compile(r"(しましょう|してください|おすすめ|意識す|練習す|準備す|やり方|手順|コツ)")
INTERVIEW_CTX = re.compile(r"(面接|選考|ES|エントリーシート|役員|人事|質疑)")


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def norm_slug(s: str) -> str:
    s = s or ""
    return s[5:] if s.startswith("slug-") else s


Q_LINE = re.compile(r"(?:^|[\s。])Q[.:：]\s*(.+?)(?=【|$)", re.S)
INTENT = re.compile(r"【[^】]*意図[^】]*】\s*([^【]{8,220})")
QUES_END = re.compile(r"(ますか|ですか|でしょうか|と思いますか|できますか|ご存じですか)")


def extract(text: str) -> list:
    """(質問, 面接官の意図, 出典文) を返す。

    三段で拾う:
      1. «Q. …» で始まる明示の質問 (大半の目标是これ。【面接官の意図】が隣に付く)
      2. 「…」で括られ ？ で終わる断片
      3. 面接語を含む ますか/ですか。で閉じる文
    助言文 («〜と答えましょう») は質問として数えない。
    """
    out = []
    t = text or ""
    for m in Q_LINE.finditer(t):
        q = re.sub(r"\s+", " ", m.group(1)).strip(" 、。")
        if len(q) < 6:
            continue
        tail = t[m.end():m.end() + 260]
        im = INTENT.search(tail)
        intent = re.sub(r"\s+", " ", im.group(1)).strip(" 、。") if im else ""
        if ADVICE.search(q) and not q.endswith(("か。", "か？", "か")):
            continue
        out.append((q[:200], intent[:220], m.group(0).strip()[:300]))
    for sent in SENT.split(t):
        s = sent.strip()
        if len(s) < 8:
            continue
        for q in QUOTED.findall(s):
            q = re.sub(r"\s+", " ", q).strip()
            if ADVICE.search(q):
                continue
            out.append((q[:200], "", s[:300]))
        if not QUOTED.search(s) and not Q_LINE.search(s):
            ends_q = s.endswith("？") or s.endswith("?") or (QUES_END.search(s) and s.endswith("。"))
            if ends_q and not ADVICE.search(s):
                out.append((s[:200], "", s[:300]))
    seen, ded = set(), []
    for q, intent, src in out:
        k = re.sub(r"\s+", "", q)[:34]
        if k in seen:
            continue
        seen.add(k)
        ded.append((q, intent, src))
    return ded


def main() -> int:
    if not SNAP.exists():
        print("  snapshot が無い")
        return 1
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    full = {}
    if FULL.exists():
        full = json.loads(FULL.read_text(encoding="utf-8"))
    corpus = json.loads(CORPUS.read_text(encoding="utf-8")) if CORPUS.exists() else []
    by_slug = {norm_slug(c.get("slug")): c for c in corpus}

    per_company = collections.defaultdict(list)
    all_q = []
    scanned = 0
    full_used = 0
    for r in snap.get("records", []):
        slug = ""
        m = re.search(r"/n/([a-z0-9]+)", r.get("url", "") or "")
        slug = m.group(1) if m else ""
        f = full.get(slug) or {}
        c = by_slug.get(slug) or {}
        text = f.get("text") or re.sub(TAG, " ", c.get("body") or "")
        text = re.sub(r"\s+", " ", text).strip()
        if f.get("chars", 0) >= 800:
            full_used += 1
        scanned += 1
        comp = (r.get("company") or "").strip()
        for q, intent, src in extract(text):
            if not (INTERVIEW_CTX.search(src) or INTERVIEW_CTX.search(r.get("title", "") or "")
                    or INTERVIEW_CTX.search(q)):
                continue
            rec = {"question": q, "intent": intent, "source_sentence": src[:300],
                   "article_title": (r.get("title") or "")[:90],
                   "url": r.get("url", ""), "price": r.get("price", 0),
                   "chars_of_source_text": len(text)}
            all_q.append(rec)
            if comp:
                per_company[comp].append(rec)

    n_comp = len(per_company)
    doc = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "text_source": ("note の記事 HTML から採った本文" if full_used > scanned * 0.5
                           else "API プレビュー混在"),
           "articles_scanned": scanned, "articles_with_full_body": full_used,
           "questions_total": len(all_q), "companies_with_questions": n_comp,
           "per_company": {k: v for k, v in sorted(per_company.items())},
           "all": all_q}
    OUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    rows = []
    for comp in sorted(per_company, key=lambda c: -len(per_company[c])):
        for rec in per_company[comp]:
            rows.append(
                f"<tr><td>{esc(comp)}</td><td>「{esc(rec['question'])}」</td>"
                f"<td>{esc(rec['intent'][:110]) if rec['intent'] else '—'}</td>"
                f"<td>{'¥' + str(rec['price']) if rec['price'] else '無料'}</td></tr>")
    top = []
    for comp in sorted(per_company, key=lambda c: -len(per_company[c]))[:20]:
        top.append("<li><strong>" + esc(comp) + "</strong>（" + str(len(per_company[comp])) + "問）："
                   + "「" + esc(per_company[comp][0]["question"]) + "」</li>")

    ld = json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "収録記事に出てくる面接質問の実文 企業別一覧",
        "description": (f"{scanned} 本の本文から質問の実文 {len(all_q)} 件を抽出、"
                        f"{n_comp} 社別に整理。各件に出典記事のURLと価格を添付。"),
        "url": f"{BASE}/interview-questions.html",
        "license": "https://creativecommons.org/licenses/by/4.0/",
    }, ensure_ascii=False, indent=1)

    doc_html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>面接で投げられた質問 {len(all_q)} 件の実文 — 企業別 | 目録</title>
<meta name="description" content="{scanned}本の収録記事から面接の質問実文{len(all_q)}件を抽出。{n_comp}社別、各件に出典URLつき。">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{BASE}/interview-questions.html">
<script type="application/ld+json">
{ld}
</script>
<style>
body{{font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif;margin:0;background:#f6f5f2;color:#1d1c1a;line-height:1.7}}
main{{max-width:1000px;margin:0 auto;padding:30px 18px 70px}}
h1{{font-size:1.3rem;margin:0 0 6px}} .sub{{color:#6d675e;font-size:.87rem;margin:0 0 16px}}
table{{width:100%;border-collapse:collapse;font-size:.84rem}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #e6e1d8;vertical-align:top}}
th{{background:#efeee9;font-weight:600}} a{{color:#7a5230}}
ol{{font-size:.88rem}} ol li{{margin:7px 0}}
.note{{font-size:.8rem;color:#6d675e;margin-top:24px}}
</style></head><main>
<h1>面接で投げられた質問 {len(all_q)} 件の実文</h1>
<p class="sub">収録記事 {scanned} 本（うち本文を HTML から取り直したもの {full_used} 本）から、
質問の実文 {len(all_q)} 件を抽出しました。助言文 («〜と答えましょう») は数えていません。
下表は {n_comp} 社に割り当てられた {sum(len(v) for v in per_company.values())} 件で、
残りの {len(all_q) - sum(len(v) for v in per_company.values())} 件は表題から企業を特定できなかったため
企業欄を外して <a href="data/interview_questions.json">JSON</a> 側に置いています。</p>

<h2 style="font-size:.98rem;margin:20px 0 8px;border-bottom:1px solid #ddd8cf;padding-bottom:5px">質問が多い順 {min(20, n_comp)} 社</h2>
<ol>
{chr(10).join(top)}
</ol>

<h2 style="font-size:.98rem;margin:24px 0 8px;border-bottom:1px solid #ddd8cf;padding-bottom:5px">全件（企業別）</h2>
<table><thead><tr><th>企業</th><th>質問の実文</th><th>面接官の意図（記事が書く範囲）</th><th>価格</th></tr></thead><tbody>
{chr(10).join(rows)}
</tbody></table>

<p class="note">更新: {time.strftime('%Y-%m-%d %H:%M JST')}（毎日 06:10 / 19:40 に自動再生成）
　抽出は機械的なので、助言文が混ざることがあります。必ず出典記事を確認してください。
　他の観測: <a href="selection-signals.html">選考段階の言及</a> ／
　<a href="es-deadlines.html">締切</a> ／ <a href="changes.html">運用履歴</a></p>
</main></body></html>"""
    OUT_HTML.write_text(doc_html, encoding="utf-8")
    print(f"  wrote interview-questions.html ({len(doc_html):,} bytes) + interview_questions.json")
    print(f"  scanned={scanned} full_body={full_used} questions={len(all_q)} companies={n_comp}")
    for comp in sorted(per_company, key=lambda c: -len(per_company[c]))[:3]:
        print(f"    ★ {comp}: {len(per_company[comp])}問  「{per_company[comp][0]['question'][:58]}」")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
