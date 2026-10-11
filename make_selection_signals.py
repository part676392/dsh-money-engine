#!/usr/bin/env python3
"""収録記事の本文から選考段階の言及を拾って企業別に集計する.

 重要な前提 (2026-10-11 実測):
   data/corpus_full.json の body は **全部 240 字**。note の公開APIが
   プレビューしか返さない。だからここでは「選考の流れ全集」を語らない。
   語るのは「600 記事の冒頭 240 字に、どの選考段階が何回出たか」だけ。
   その代わり一本ずつ引用文を添えるので、検証できる。

 出力:
   data/selection_signals.json   企業別 + 集計
   selection-signals.html        公開頁 (Dataset 構造化データ付き)
"""
from __future__ import annotations

import buy_block
BUY = buy_block.html()
import collections
import html
import json
import pathlib
import re
import time

ROOT = pathlib.Path(__file__).resolve().parent
CORPUS = ROOT / "data" / "corpus_full.json"
FULL = ROOT / "data" / "full_bodies.json"   # note の HTML から取り直した太い本文
SNAP = ROOT / "data" / "snapshot-latest.json"
OUT_JSON = ROOT / "data" / "selection_signals.json"
OUT_HTML = ROOT / "selection-signals.html"
BASE = "https://part676392.github.io/dsh-money-engine"

# 選考段階と形式の語彙。 Detection はこの語を含む"文"だけを採用する。
STAGES = [
    ("書類選考", ("書類選考", "書類通過", "書類で")),
    ("適性検査", ("適性検査", "SPI", "TG-WEB", "玉手箱", "Webテスト")),
    ("一次面接", ("一次面接", "1次面接", "第一次面接")),
    ("二次面接", ("二次面接", "2次面接")),
    ("最終面接", ("最終面接", "最後面接")),
    ("人事面接", ("人事面接",)),
    ("現場面接", ("現場面接", "所属長面接", "配属先面接")),
    ("技術面接", ("技術面接", "専門面接")),
    ("グループ面接", ("グループ面接", "集団面接")),
    ("個人面接", ("個人面接", "一対一", "1対1")),
    ("AI・録画", ("AI面接", "録画面接", "動画面接", "AI選考", "AIエージェント")),
    ("オンライン", ("Web面接", "オンライン面接", "Zoom面接", "Teams面接")),
    ("課題・筆記", ("課題提出", "課題あり", "筆記試験", "小論文", "ケース問題")),
    ("体験勤務", ("体験面接", "職場体験", "インターン選考")),
]
SENT_SPLIT = re.compile(r"(?<=[。！？])\s*")
TAG = re.compile(r"<[^>]+>")


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def norm_slug(s: str) -> str:
    s = s or ""
    return s[5:] if s.startswith("slug-") else s


def main() -> int:
    if not CORPUS.exists() or not SNAP.exists():
        print("  corpus / snapshot が無い")
        return 1
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    by_slug = {norm_slug(c.get("slug")): c for c in corpus}
    # 太い本文 (harvest_full.py) が有ればそれを優先。API の 240 字は最後の代替。
    full = {}
    if FULL.exists():
        try:
            full = json.loads(FULL.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            full = {}
    src_mode = "full HTML body" if full else "API preview (240字)"
    src_word2 = "全文" if full else "本文プレビュー"
    if full:
        avg = sum(len(str(v.get("text") or "")) for v in full.values()
                  if isinstance(v, dict)) // max(len(full), 1)
        src_line = (f"本文は note の記事ページから取り直した<strong>全文</strong>です"
                    f"（{len(full)} 本・平均 {avg:,} 字）。")
    else:
        src_line = ("本文は note の公開APIが返す <strong>プレビュー 240 字</strong> です"
                    f"（全 {matched_articles} 本が 240 字）。")

    per_company: dict = {}
    stage_total = collections.Counter()
    stage_companies = collections.defaultdict(set)
    matched_articles = 0
    quoted = 0
    body_lens = collections.Counter()

    for r in snap.get("records", []):
        m = re.search(r"/n/([a-z0-9]+)", r.get("url", "") or "")
        slug = m.group(1) if m else None
        c = by_slug.get(slug)
        if not c:
            continue
        f = full.get(slug) or {}
        raw_text = f.get("text") or c.get("body") or ""
        body = re.sub(TAG, " ", raw_text)
        body = re.sub(r"\s+", " ", body).strip()
        body_lens[len(body)] += 1
        matched_articles += 1
        comp = (r.get("company") or "").strip()
        found_any = False
        for sent in SENT_SPLIT.split(body):
            sent = sent.strip()
            if len(sent) < 8:
                continue
            for stage, keys in STAGES:
                if any(k in sent for k in keys):
                    found_any = True
                    stage_total[stage] += 1
                    if comp:
                        stage_companies[stage].add(comp)
                        row = per_company.setdefault(comp, {})
                        e = row.setdefault(stage, {"count": 0, "quotes": [], "articles": []})
                        e["count"] += 1
                        if len(e["quotes"]) < 2:
                            e["quotes"].append(sent[:160])
                            quoted += 1
                        if r.get("url") and len(e["articles"]) < 3:
                            e["articles"].append({"title": r.get("title", "")[:80],
                                                  "url": r.get("url", ""),
                                                  "price": r.get("price", 0)})
        if found_any:
            pass

    n_comp = len(per_company)
    doc = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "text_source": src_mode,
    "method": ("本文を文単位に切り、"
                   "選考段階の語を含む文だけを採用。引用文は抽出そのまま。"),
        "caveat": ("採ったのは収録記事の本文から。ただし公開しているのは各言及の引用1文と"
                   "リンクだけで、本文の再発行はしていない。選考工程の全集でもない。"),
        "articles_scanned": matched_articles,
        "body_length_distribution": {str(k): v for k, v in body_lens.most_common(5)},
        "companies_with_mentions": n_comp,
        # 帰属の強さを測る: 企業名が本文か表題に出る行の割合。
        # ただし企業名自体を表題から取っているので、これは循環的な検証だと明記する。
        "attribution_note": ("企業は記事の表題から割り出した。よって『企業名が本文か表題に"
                             "出る』という検証は循環的で、引用した文が実際にその企業の選考を"
                             "記述しているとまでは保証しない。載せるのは言及の実数だけ。"),
        "stage_totals": dict(stage_total.most_common()),
        "companies_per_stage": {k: len(v) for k, v in sorted(stage_companies.items(),
                                                            key=lambda x: -len(x[1]))},
        "per_company": {k: {s: v for s, v in sorted(rows.items())}
                        for k, rows in sorted(per_company.items())},
    }
    OUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    rows = []
    for comp in sorted(per_company, key=lambda c: -sum(v["count"] for v in per_company[c].values())):
        cells = []
        for stage, e in sorted(per_company[comp].items()):
            q = esc(e["quotes"][0]) if e["quotes"] else ""
            cells.append(f"<tr><td>{esc(comp)}</td><td>{esc(stage)}</td>"
                         f"<td>{e['count']}</td><td>「{q}」</td>"
                         f"<td>{esc(', '.join(a['url'].split('/n/')[-1][:12] for a in e['articles']))}</td></tr>")
        rows.extend(cells)
    total_mentions = sum(stage_total.values())

    agg_rows = "\n".join(
        f"<tr><td>{esc(s)}</td><td>{stage_total[s]}</td><td>{len(stage_companies[s])}</td></tr>"
        for s, _ in stage_total.most_common())

    ld = json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "収録記事に現れた選考段階の言及 企業別集計",
        "description": (f"{matched_articles} 本の {src_word2}から選考段階の語を含む文を抽出し、"
                        f"{n_comp} 社別に集計 ({total_mentions} 言及)。各言及に引用文を添付。"),
        "creator": {"@type": "Person", "name": "転職ナビ・中途キャリアの研究所"},
        "url": f"{BASE}/selection-signals.html",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "creditText": "CC BY 4.0 は抽出した表・順序・対応づけにだけ適用します。本文の著作権は note の各記事の著者に帰属し、引用は出典URLつきで最小限に留めています。",
        "isBasedOn": "https://note.com/shushoku_career1",
    }, ensure_ascii=False, indent=1)

    doc_html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>収録記事に現れた選考段階 {total_mentions} 言及 — 企業別集計 | 目録</title>
<meta name="description" content="{matched_articles}本の本文から選考段階の語を含む文だけを抽出し、{n_comp}社別に集計。各言及に引用文つき。">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{BASE}/selection-signals.html">
<script type="application/ld+json">
{ld}
</script>
<style>
body{{font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif;margin:0;background:#f6f5f2;color:#1d1c1a;line-height:1.7}}
main{{max-width:980px;margin:0 auto;padding:30px 18px 70px}}
h1{{font-size:1.3rem;margin:0 0 6px}} .sub{{color:#6d675e;font-size:.87rem;margin:0 0 16px}}
.caution{{background:#fff6e8;border:1px solid #e7cf9f;border-radius:8px;padding:12px 15px;font-size:.87rem;margin:14px 0 20px}}
table{{width:100%;border-collapse:collapse;font-size:.83rem}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #e6e1d8;vertical-align:top}}
th{{background:#efeee9;font-weight:600}}
a{{color:#7a5230}} code{{background:#eceae4;padding:1px 5px;border-radius:4px;font-size:.76rem}}
.note{{font-size:.8rem;color:#6d675e;margin-top:24px}}
</style></head><main>
<h1>収録記事に現れた選考段階 {total_mentions} 言及</h1>
<p class="sub">{matched_articles} 本の本文から、選考段階の語を含む文だけを機械抽出し、企業別に集計しました。各行に引用文を載せています。</p>

<div class="caution"><strong>この頁で言えること。</strong>
{src_line}
したがってこれは「収録記事の冒頭に現れた選考段階の言及」であって、<strong>各社の選考工程の全集ではありません</strong>。
さらにひとつ：<strong>ここに載っているのは「言及」であって「実施」ではありません</strong>。収録記事は企業向けの助言を含むため、
「書類選考は通るのに」という定型文がその企業の選考を語っているとは限りません。工程の実在を確認するには引用元の記事と各社の採用ページを突き合わせてください。</div>

<h2 style="font-size:.98rem;margin:24px 0 8px;border-bottom:1px solid #ddd8cf;padding-bottom:5px">段階別の出現回数</h2>
<table><thead><tr><th>選考段階</th><th>言及</th><th>言及された社</th></tr></thead><tbody>
{agg_rows}
</tbody></table>

<h2 style="font-size:.98rem;margin:24px 0 8px;border-bottom:1px solid #ddd8cf;padding-bottom:5px">企業別（言及順・引用つき）</h2>
<table><thead><tr><th>企業</th><th>段階</th><th>回数</th><th>収録記事に出てきた文</th><th>記事</th></tr></thead><tbody>
{chr(10).join(rows)}
</tbody></table>

<p class="note"><b>権利の範囲:</b> CC BY 4.0 は抽出した表・順序・対応づけにだけ適用します。本文の著作権は note の各記事の著者に帰属し、この頁にあるのは出典URLつきの最小限の引用です。<br>更新: {time.strftime('%Y-%m-%d %H:%M JST')}（毎日 06:10 / 19:40 に自動再生成）　抽出方法: 文単位に分割し、語彙を含む文のみ採用。引用は抽出そのまま。
　他の観測の積み上がりは <a href="changes.html">運用履歴</a>、検索需要は <a href="ai-interviews.html">AI・録上面接の需要語</a> に公開しています。</p>
{BUY}</main></body></html>"""
    OUT_HTML.write_text(doc_html, encoding="utf-8")
    print(f"  wrote selection-signals.html ({len(doc_html):,} bytes) + selection_signals.json")
    print(f"  articles={matched_articles} companies={n_comp} mentions={total_mentions} quotes={quoted}")
    print(f"  top stages: {', '.join(f'{k}={v}' for k, v in stage_total.most_common(5))}")
    print(f"  body 長分布: {dict(body_lens.most_common(3))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
