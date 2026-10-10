#!/usr/bin/env python3
"""収録記事が引用している「公式の選考フロー」を順序付きで企業別に集める.

 動機: 太い本文 (harvest_full.py) を見たら、記事が公式ページの選考工程を
 そのまま `書類選考 → SPI → 面接(複数回)` の形で引用していた。
 これは目録の中で一番堀になる列だと思う。理由は、
   · 順序 (何を何回やるか) が構造化されている
   · 「公式に示されています」等の一次情報引用として出典が attached できる
   · 他人が後から作っても、いつの時点の公式か history が無いと検証できない
 だから取った物は全部 取得日時付き で積む。

 手順:
   1. «選考の流れ: … → …» を拾う
   2. 前後の語り ("公式の職種ページでは、…案内されています。") を落す
   3. 枠 (職種の別) が同じ文に複数あれば分ける
   4. 工程名を正規カテゴリに寄せる (寄せた元の名前も残す)
   5. 企業別に出典ついでで積む
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
OUT_JSON = ROOT / "data" / "selection_flows.json"
OUT_HTML = ROOT / "selection-flows.html"
BASE = "https://part676392.github.io/dsh-money-engine"

TAG = re.compile(r"<[^>]+>")
FLOW = re.compile(r"(?:選考の流れ|選考フロー|選考ステップ|選考プロセス|採用の流れ)\s*[:：]?\s*([^|｜\n]{15,260})")
ARROW = re.compile(r"\s*(?:→|->|➔|＞)\s*")
# 語り落し: 最初の工程より前の "〜案内されています。" 等を捨てる
NARRATIVE = re.compile(r"^.*?(?:案内されています|示されています|記載があります|次の通り|次のように|以下).{0,4}", re.S)
QUOTE_MARK = re.compile(r"^\s*[>»「]?\s*")

# 正規カテゴリ: 順番は「早い順」。matches は部分一致で拾う。
CANON = [
    ("会社説明会", ("会社説明会", "説明会", "カジュアル面談", "プレ面接")),
    ("エントリー", ("エントリー", "応募フォーム", "応募登録", "マイページ登録", "登録")),
    ("書類選考", ("書類選考", "履歴書", "ES", "エントリーシート", "書類")),
    ("適性検査", ("適性検査", "SPI", "Webテスト", "WEBテスト", "オンラインテスト", "玉手箱", "TG-WEB")),
    ("AI・録画面接", ("AI面接", "録画面接", "動画面接", "AI選考", "AIエージェント")),
    ("課題・筆記", ("課題", "筆記", "小論文", "ケース", "テスト", "専門試験")),
    ("グループワーク", ("グループワーク", "グループ討論", "グループ面接", "集団面接")),
    ("一次面接", ("一次面接", "1次面接", "第一次面接", "一回目", "1回目の面接")),
    ("二次面接", ("二次面接", "2次面接", "二回目", "2回目の面接", "第二次面接")),
    ("最終面接", ("最終面接", "3次面接", "三次面接", "役員面接", "社長面接")),
    ("追加面接", ("面接（複数回）", "面接(複数回)", "面接2回", "面接（2回）", "面接（3回）",
                 "追加面接", "再面接")),
    ("バックグラウンドチェック", ("バックグラウンドチェック", "リファレンス", "身元確認")),
    ("オファー面談", ("オファー面談", "条件提示", "内定連絡", "内々定", "内定", "採用決定", "入社")),
]


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def canon_of(step: str) -> str:
    s = step.strip()
    for label, keys in CANON:
        if any(k in s for k in keys):
            return label
    return "その他"


PREFIX_NOISE = re.compile(
    r"^(?:（[^）]{0,24}）|\([^)]{0,24}\)|"
    r"一般的には|おおむね|だいたい|通常|一般的な例|公式では|公式の[^、。：]{0,28}では|"
    r"公式の[^、。：]{0,28}によると|多くの企業では|中途では|新卒では)[、。:：\s]*")


def clean_segment(seg: str) -> str:
    s = NARRATIVE.sub("", seg)
    s = QUOTE_MARK.sub("", s)
    for _ in range(3):
        s2 = PREFIX_NOISE.sub("", s)
        if s2 == s:
            break
        s = s2
    return s.strip(" 、。・|｜")


def flows_from(text: str) -> list:
    """[({'track': str, 'raw': str, 'steps': [{'raw','canon'}]} , 出典文)]"""
    out = []
    for m in FLOW.finditer(text or ""):
        seg = m.group(1)
        if "→" not in seg and "->" not in seg:
            continue
        # 1文に複数の枠があれば «枠名：A → B → C» で分ける
        parts = re.split(r"(?:[。]\s*|[；;]\s*)(?=[^→]{2,26}[：:])", clean_segment(seg))
        for p in parts:
            if "→" not in p and "->" not in p:
                continue
            track = ""
            tm = re.match(r"\s*([^：:→]{2,28})[：:]\s*", p)
            if tm:
                track = tm.group(1).strip()
                p = p[tm.end():]
            raw_steps = [s.strip(" 、。") for s in ARROW.split(p) if s.strip(" 、。")]
            raw_steps = [s for s in raw_steps if 1 <= len(s) <= 40]
            if len(raw_steps) < 2:
                continue
            steps = [{"raw": s, "canon": canon_of(s)} for s in raw_steps]
            out.append({"track": track, "raw": " → ".join(raw_steps)[:260], "steps": steps,
                        "sentence": m.group(0).strip()[:300]})
    return out


# 他頁への相互リンクに載せる数字は data から読む。直書きは枯れる (実測: 1,873 が旧値で残った)。
try:
    _j = json.loads((ROOT / "data" / "interview_questions.json").read_text(encoding="utf-8"))
    NQ = f"{int(_j.get('questions_total', 0)):,}"
except Exception:  # noqa: BLE001
    NQ = "?"


def main() -> int:

    if not FULL.exists():
        print("  full_bodies.json が無い (harvest_full.py を先に)")
        return 1
    full = json.loads(FULL.read_text(encoding="utf-8"))
    per_company = collections.defaultdict(list)
    canon_count = collections.Counter()
    canon_companies = collections.defaultdict(set)
    total_flows = 0
    companies = set()
    for slug, v in full.items():
        text = re.sub(r"\s+", " ", re.sub(TAG, " ", v.get("text") or "")).strip()
        comp = (v.get("company") or "").strip()
        for f in flows_from(text):
            total_flows += 1
            for st in f["steps"]:
                canon_count[st["canon"]] += 1
                if comp:
                    canon_companies[st["canon"]].add(comp)
            if comp:
                companies.add(comp)
                per_company[comp].append({**f, "url": v.get("url", ""),
                                          "price": v.get("price", 0),
                                          "title": (v.get("title") or "")[:80]})

    # 面接回数の分布 (何回面接を挟むか) — 求職者が一番知りたい数
    iv_counts = collections.Counter()
    for comp, rows in per_company.items():
        for r in rows:
            n = sum(1 for s in r["steps"] if s["canon"] in
                    ("一次面接", "二次面接", "最終面接", "追加面接", "グループワーク", "AI・録画面接"))
            iv_counts[n] += 1

    doc = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "method": ("記事本文から «選考の流れ：…→…» を抽出。前後の語りを落し、"
                      "工程名を正規カテゴリに寄せた (寄せた元の名前も raw に保持)。"),
           "caveat": ("中身は収録記事が『公式に示されています』等に引いた文の機械抽出。"
                      "公式ページの現在の表記とは違う可能性がある。各件に出典記事URLを添付した。"),
           "articles_scanned": len(full), "flows_total": total_flows,
           "companies_with_flows": len(per_company),
           "step_frequency": dict(canon_count.most_common()),
           "companies_per_step": {k: len(v) for k, v in sorted(
               canon_companies.items(), key=lambda x: -len(x[1]))},
           "interview_round_distribution": {str(k): v for k, v in sorted(iv_counts.items())},
           "per_company": {k: v for k, v in sorted(per_company.items())}}
    OUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    order = [c for c, _ in CANON] + ["その他"]
    agg = "\n".join(
        f"<tr><td>{esc(c)}</td><td>{canon_count[c]}</td><td>{len(canon_companies[c])}</td></tr>"
        for c in order if canon_count.get(c))
    rows = []
    for comp in sorted(per_company):
        for r in per_company[comp]:
            chips = " ".join(
                f'<span class="s {"o" if s["canon"] != "その他" else "u"}" title="{esc(s["raw"])}">'
                f'{esc(s["canon"] if s["canon"] != "その他" else s["raw"][:14])}</span>'
                for s in r["steps"])
            rows.append(f"<tr><td>{esc(comp)}</td>"
                        f"<td>{esc(r['track']) if r['track'] else '—'}</td>"
                        f"<td class=flow>{chips}</td>"
                        f"<td>{'¥' + str(r['price']) if r['price'] else '無料'}</td></tr>")
    LABEL = {0: "0回（フローの文に面接語が無く数えられない）"}
    dist = "　".join(f"<b>{LABEL.get(k, str(k) + '回')}</b>: {v}本" for k, v in sorted(iv_counts.items()))

    ld = json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "企業の公式選考フロー 順序付き 企業別集計",
        "description": (f"収録記事が引用した公式の選考工程 {total_flows} 本を順序付きで整理、"
                        f"{len(per_company)} 社別に公開。各工程は正規カテゴリに寄せる前の表記も保持し、"
                        f"出典記事のURLを添付している。"),
        "url": f"{BASE}/selection-flows.html",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "creditText": "CC BY 4.0 は抽出した表・順序・対応づけにだけ適用します。本文の著作権は note の各記事の著者に帰属し、引用は出典URLつきで最小限に留めています。",
        "isBasedOn": "https://note.com/shushoku_career1",
    }, ensure_ascii=False, indent=1)

    doc_html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>企業の公式選考フロー {total_flows} 本・{len(per_company)} 社（順序つき）| 目録</title>
<meta name="description" content="収録記事が引用した公式の選考工程{total_flows}本を順序付きで整理。{len(per_company)}社別、工程の本来の表記と出典URLつき。">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{BASE}/selection-flows.html">
<script type="application/ld+json">
{ld}
</script>
<style>
body{{font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif;margin:0;background:#f6f5f2;color:#1d1c1a;line-height:1.7}}
main{{max-width:1060px;margin:0 auto;padding:30px 18px 70px}}
h1{{font-size:1.3rem;margin:0 0 6px}} .sub{{color:#6d675e;font-size:.87rem;margin:0 0 14px}}
.caution{{background:#fff6e8;border:1px solid #e7cf9f;border-radius:8px;padding:12px 15px;font-size:.86rem;margin:14px 0 18px}}
table{{width:100%;border-collapse:collapse;font-size:.83rem}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #e6e1d8;vertical-align:top}}
th{{background:#efeee9;font-weight:600}} a{{color:#7a5230}}
.flow{{max-width:640px}}
.s{{display:inline-block;background:#e8f0ff;color:#1a4fa0;border-radius:14px;padding:1px 8px;margin:2px 2px 2px 0;font-size:.76rem}}
.s.u{{background:#f0ece4;color:#6d675e}}
.dist{{background:#fff;border:1px solid #e6e1d8;border-radius:8px;padding:10px 14px;font-size:.85rem;margin:12px 0}}
.note{{font-size:.8rem;color:#6d675e;margin-top:24px}}
</style></head><main>
<h1>企業の公式選考フロー {total_flows} 本・{len(per_company)} 社</h1>
<p class="sub">収録記事 {len(full)} 本の本文から、記事が公式ページに引いた «選考の流れ：… → …» を機械抽出して順序付きに整理しました。
うち <b>{sum(len(v) for v in per_company.values())} 本</b>を表に載せています（{len(per_company)} 社に割当）。
残りの {total_flows - sum(len(v) for v in per_company.values())} 本は表題から企業を特定できなかったもので、
<a href="data/selection_flows.json">JSON</a> の全 {total_flows} 本側に入っています。</p>

<div class="caution"><strong>この頁の数字の出し方。</strong>
工程名はこちらで正規カテゴリに寄せています（例 «SPI試験(WEB)» → 適性検査）。寄せた<b>前の表記</b>は
各チップに title として入れ、JSON には <code>raw</code> で全件残しています。
中身は収録記事が「公式に示されています」等に書いた文の抽出で、<b>公式ページの現在の表記とは違う可能性があります</b>。
各社の確認用に出典記事のURLを JSON につけています。</div>

<div class="dist"><b>フローの中で面接系ステップが数本現れたか（{total_flows}本）</b><br>{dist}</div>

<h2 style="font-size:.98rem;margin:22px 0 8px;border-bottom:1px solid #ddd8cf;padding-bottom:5px">工程が現れた回数</h2>
<table><thead><tr><th>工程（正規）</th><th>出現</th><th>関連企業</th></tr></thead><tbody>
{agg}
</tbody></table>

<h2 style="font-size:.98rem;margin:24px 0 8px;border-bottom:1px solid #ddd8cf;padding-bottom:5px">企業別の順序</h2>
<table><thead><tr><th>企業</th><th>枠</th><th>選考の順序</th><th>出典記事の価格</th></tr></thead><tbody>
{chr(10).join(rows)}
</tbody></table>

<p class="note"><b>権利の範囲:</b> CC BY 4.0 は抽出した表・順序・対応づけにだけ適用します。本文の著作権は note の各記事の著者に帰属し、この頁にあるのは出典URLつきの最小限の引用です。<br>更新: {time.strftime('%Y-%m-%d %H:%M JST')}（毎日 06:10 / 19:40 に自動再生成・取得日時付き）
　機械抽出なので枠の切れ目がずれることがあります。生データ: <a href="data/selection_flows.json">data/selection_flows.json</a>
　他の観測: <a href="interview-questions.html">面接質問 {NQ} 問</a> ／
　<a href="selection-signals.html">選考段階の言及</a> ／ <a href="changes.html">運用履歴</a></p>
</main></body></html>"""
    OUT_HTML.write_text(doc_html, encoding="utf-8")
    print(f"  wrote selection-flows.html ({len(doc_html):,} bytes) + selection_flows.json")
    narr = [r["raw"] for rows in per_company.values() for r in rows
            if re.match(r"^(一般的|公式|多く|だいたい|通常)", r["raw"])]
    print(f"  scanned={len(full)} flows={total_flows} companies={len(per_company)} "
          f"語り残骸={len(narr)}")
    print(f"  面接回数分布: {dist}")
    for comp in list(sorted(per_company))[:3]:
        r = per_company[comp][0]
        print(f"    ★ {comp}: {r['raw'][:88]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
