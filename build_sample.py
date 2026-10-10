#!/usr/bin/env python3
"""納品物の実物見本をつくる.

 動機: 販売頁 (data-license.html) には価格しかなかった。買い手は
 「自分が受け取る CSV がどんな形か」を見る場所が無い (2026-10-11 実測: 見本 0)。
 そこで 3社ぶんの完全な抽出をそのまま出し、CSV も同じ形で落とす。
 会社を1社にしない理由: 面接官の意図を持つ記事は一部なので、
 1社だと目玉の列が空になり商品が見えない。
"""
from __future__ import annotations

import csv
import html
import io
import json
import pathlib
import time
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent
BASE = "https://part676392.github.io/dsh-money-engine"
OUT = ROOT / "sample.html"
EXP = ROOT / "exports"
DATA = ROOT / "data"
N_COMPANIES = 3


def tracker(key: str) -> str:
    """访问計 (build_store.py と同じ作り方)。"""
    return (
        '<script>(function(){try{var b="'
        + "https://abacus.jasoncameron.dev/hit/dsh-money-engine/"
        + '";fetch(b+"'
        + key
        + '", {mode:"no-cors",keepalive:true});'
        + "var m=(location.search.match(/[?&]src=([a-z0-9_-]{1,24})/)||[])[1];"
        + "if(m){fetch(b+'src-'+m, {mode:'no-cors',keepalive:true});}"
        + "}catch(e){}})();</script>"
    )


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def load(p: str, default=None):
    f = DATA / p
    if not f.exists():
        return {} if default is None else default
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def pick(q: dict, fl: dict, sg: dict) -> list:
    """物が一番揃っている企業を N 社 (意図が1つ以上ある社を必ず1社含める)。"""
    pc, pf, ps = q.get("per_company") or {}, fl.get("per_company") or {}, sg.get("per_company") or {}
    scored = []
    for c in set(list(pc) + list(pf) + list(ps)):
        items = pc.get(c) or []
        nq = len(items)
        ni = sum(1 for it in items if (it.get("intent") or "").strip())
        nf = len(pf.get(c) or [])
        ns = sum(o.get("count", 0) for o in (ps.get(c) or {}).values())
        scored.append({"company": c, "q": nq, "intent": ni, "flow": nf, "sig": ns,
                       "score": nq + nf * 8 + ni * 3 + ns})
    scored.sort(key=lambda d: -d["score"])
    top = scored[:N_COMPANIES]
    if not any(d["intent"] for d in top):
        with_intent = [d for d in scored if d["intent"]]
        if with_intent:
            top[-1] = with_intent[0]
    return top


def main() -> int:
    q, fl, sg = load("interview_questions.json"), load("selection_flows.json"), load("selection_signals.json")
    lnp = load("question_lineups.json")
    picks = pick(q, fl, sg)
    if not picks:
        print("  企業が無い: 見本を作れない")
        return 1
    companies = [d["company"] for d in picks]

    # --- CSV (納品物と同じ縦長形) ---
    EXP.mkdir(exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["company", "record_type", "index", "content", "interviewer_intent",
                "step_category", "source_url", "source_price_yen"])
    rows = 0
    for c in companies:
        for i, it in enumerate(q.get("per_company", {}).get(c) or [], 1):
            w.writerow([c, "question", i, it.get("question", ""), it.get("intent", ""),
                        "", it.get("url", ""), it.get("price", "")])
            rows += 1
        for fi, f in enumerate(fl.get("per_company", {}).get(c) or [], 1):
            for si, st in enumerate(f.get("steps", []), 1):
                w.writerow([c, f"flow#{fi}", si, st.get("raw", ""), "", st.get("canon", ""),
                            f.get("url", ""), f.get("price", "")])
                rows += 1
        o = lnp.get("per_company", {}).get(c) or {}
        for li, entry in enumerate(o.get("lineups") or [], 1):
            for pi, cat in enumerate(entry.get("order") or [], 1):
                w.writerow([c, f"lineup#{li}", pi, cat, "", "", o.get("url", ""), o.get("price", "")])
                rows += 1
        for stage, obj in (sg.get("per_company", {}).get(c) or {}).items():
            for quote in (obj.get("quotes") or []):
                urls = " ".join(a.get("url", "") for a in (obj.get("articles") or []))
                w.writerow([c, "signal", "", quote, "", stage, urls, ""])
                rows += 1
    cpath = EXP / "sample_dossier.csv"
    cpath.write_text(buf.getvalue(), encoding="utf_8_sig")

    # --- 頁 ---
    blocks = []
    for d in picks:
        c = d["company"]
        items = q.get("per_company", {}).get(c) or []
        qs = "\n".join(
            f"<tr><td>{i}</td><td>{esc(it.get('question',''))}</td>"
            f"<td>{esc(it.get('intent','') or '—')}</td>"
            f"<td><a href=\"{esc(it.get('url',''))}\">出典</a> "
            f"{'🆓' if not str(it.get('price','')).strip(' 0') else '¥' + esc(it.get('price',''))}</td></tr>"
            for i, it in enumerate(items, 1)) or '<tr><td colspan="4">質問の実文なし</td></tr>'
        frow = []
        for f in fl.get("per_company", {}).get(c) or []:
            steps = " → ".join(esc(s.get("canon", "")) for s in f.get("steps", []))
            raw = " ／ ".join(esc(s.get("raw", "")) for s in f.get("steps", []))
            frow.append(f"<p><b>{esc(f.get('track','') or '本流')}</b>: {steps}</p>"
                        f"<p class='raw'>元の表記: {raw}</p>")
        flows = "\n".join(frow) or "<p>フローの記載なし</p>"
        o = lnp.get("per_company", {}).get(c) or {}
        lu = (o.get("lineups") or [{}])[0].get("order") or []
        lineup = ('<ol>' + "".join(f"<li>{esc(x)}</li>" for x in lu) + "</ol>"
                  if lu else "<p>目次の記載なし</p>")
        n_lu = len(o.get("lineups") or [])
        sig = "\n".join(
            f"<li><b>{esc(stage)}</b> ×{obj.get('count',0)}: "
            f"「{esc((obj.get('quotes') or ['—'])[0][:150])}」</li>"
            for stage, obj in (sg.get("per_company", {}).get(c) or {}).items()) or "<li>記載なし</li>"
        blocks.append(f"""
<section class="co">
<h2>{esc(c)}</h2>
<p class="met">質問 {d['q']} 問 (意図つき {d['intent']}) ／ 公式フロー {d['flow']} 本 ／ 段階の言及 {d['sig']} 箇所</p>
<p class="ord">質問カテゴリの並び: {esc(" → ".join((lnp.get("per_company", {}).get(d['company'], {}) or {}).get("lineups", [{}])[0].get("order", [])[:10])) if ((lnp.get("per_company", {}).get(d['company'], {}) or {}).get("lineups")) else "記載なし"}</p>
<h3>面接で投げられた質問の実文</h3>
<table><thead><tr><th>#</th><th>質問</th><th>面接官の意図（記事が書いた分だけ）</th><th>出典</th></tr></thead>
<tbody>{qs}</tbody></table>
<h3>公式の選考フロー</h3>{flows}
<h3>質問カテゴリの並び (記事の目次から)</h3>{lineup}
<h3>選考段階の言及（1文引用）</h3><ul>{sig}</ul>
</section>""")

    total_q = sum(d["q"] for d in picks)
    total_i = sum(d["intent"] for d in picks)
    total_f = sum(d["flow"] for d in picks)
    ld = json.dumps({
        "@context": "https://schema.org", "@type": "ItemPage",
        "name": "カスタム抽出の納品物見本 (3社)",
        "mainEntity": {
            "@type": "Dataset",
            "name": "納品物見本: 面接質問・公式選考フロー・選考段階 (3社)",
            "description": (f"株式会社ディスコほか {len(picks)} 社ぶんの実物見本。"
                            f"面接質問 {total_q} 問 (面接官の意つき {total_i})、"
                            f"公式選考フロー {total_f} 本、選考段階の引用つき。"),
            "url": f"{BASE}/sample.html",
            "distribution": {"@type": "DataDownload", "encodingFormat": "text/csv",
                             "contentUrl": f"{BASE}/exports/sample_dossier.csv"},
            "creditText": ("CC BY 4.0 は抽出した表・順序・対応づけにだけ適用します。"
                           "記事本文の著作権は note の各記事の著者に帰属します。"),
            "isBasedOn": "https://note.com/shushoku_career1",
        },
    }, ensure_ascii=False, indent=1)

    doc = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>納品物見本 — 面接質問と選考フローのCSV ({total_q}問) | 目録</title>
<meta name="description" content="カスタム抽出の納品物見本。{len(picks)}社ぶん、面接質問 {total_q} 問（意図つき {total_i}）、公式選考フロー {total_f} 本、出典URLつき。CSV 付き。">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{BASE}/sample.html">
{tracker("sample")}
<script type="application/ld+json">
{ld}
</script>
<style>
body{{font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif;margin:0;background:#f6f5f2;color:#1d1c1a;line-height:1.65}}
main{{max-width:980px;margin:0 auto;padding:30px 16px 70px}}
h1{{font-size:1.3rem;margin:0 0 6px}} h2{{font-size:1.05rem;margin:24px 0 4px;border-left:4px solid #7a5230;padding-left:9px}}
h3{{font-size:.92rem;margin:14px 0 4px;color:#4c463e}}
.sub{{color:#6d675e;font-size:.87rem;margin:0 0 14px}}
.cta{{background:#fff;border:1px solid #e0d8ca;border-radius:9px;padding:12px 15px;font-size:.88rem;margin:14px 0}}
table{{width:100%;border-collapse:collapse;font-size:.85rem;margin:6px 0}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #ece7de;vertical-align:top}}
th{{background:#efeee9}} .met{{font-size:.82rem;color:#6d675e;margin:2px 0 8px}}
.raw{{font-size:.78rem;color:#6d675e;margin:2px 0 8px}}
.co{{background:#fff;border:1px solid #ece7de;border-radius:9px;padding:6px 14px 12px;margin:14px 0}}
ul{{font-size:.85rem}} li{{margin:5px 0}}
.note{{font-size:.8rem;color:#6d675e;margin-top:24px}} a{{color:#7a5230}}
</style></head><main>
<h1>納品物見本（実物です）</h1>
<p class="sub">有料の「カスタム抽出」で届く CSV を、そのままここに載せています。3社ぶんです。</p>

<div class="cta"><b>この形で届きます</b>: <a href="exports/sample_dossier.csv">sample_dossier.csv</a>
（UTF-8 BOM 付き／縦長1行1記録／列は <code>company, record_type, index, content, interviewer_intent, step_category, source_url, source_price_yen</code>）<br>
見積り・注文のしかたは <a href="data-license.html">データ資産の購入</a> に書いてあります。
今この頁にある {rows} 行ぶんが、paid 版では <b>〜50社で $15</b> です。</div>

{''.join(blocks)}

<div class="cta"><b>意図の列が空の企業がある理由</b>: 面接官の意図を書いている記事と書いていない記事があります。
空を埋めるために推測で文を作ると、それはもう事実ではないので空のままにしています。</div>

<p class="note">更新: {time.strftime('%Y-%m-%d %H:%M JST')}（毎日 06:10 / 19:40 に自動再生成）
　出典: <a href="https://note.com/shushoku_career1">note / 転職ナビ・中途キャリアの研究所</a>
　権利: 記事本文の著作権は各記事の著者に帰属。ここにあるのは抽出した表・順序・対応づけと1文の引用です。
　<a href="data-license.html">購入</a> ／ <a href="exports/sample_dossier.csv">CSV</a> ／ <a href="./">目録へ</a></p>
</main></body></html>"""
    OUT.write_text(doc, encoding="utf-8")
    print(f"  wrote sample.html ({len(doc):,} chars) + exports/sample_dossier.csv ({cpath.stat().st_size:,}B)")
    for d in picks:
        print(f"    {d['company'][:30]:32s} q={d['q']:3d} intent={d['intent']:2d} flow={d['flow']} sig={d['sig']}")
    print(f"  CSV 行数={rows}  質問合計={total_q} 意図つき={total_i} フロー={total_f}")
    assert rows > 0 and total_q > 0, "見本が空"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
