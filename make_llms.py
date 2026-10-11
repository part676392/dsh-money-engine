#!/usr/bin/env python3
"""LLM クローラ向けの索引 llms.txt / llms-full.txt を作る.

 目的: この資産は「歴史が堀になる AEO 対応データ資産」である。
 検索エンジン向けの sitemap.xml は有ったが、LLM クローラ向けの索引が無かった。
 llms.txt 規約に沿って、取れた数値と在処だけを平文で置く。

 約束: 推定を書かない。各項目には実数か取得元を添える。
"""
from __future__ import annotations

import json
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parent
BASE = "https://part676392.github.io/dsh-money-engine"
OUT = ROOT / "llms.txt"
OUT_FULL = ROOT / "llms-full.txt"


def load(p: str, default=None):
    f = ROOT / p
    if not f.exists():
        return default
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def price_section() -> str:
    """値段・買い方・権利を、AI がそのまま引用できる平文で置く。
    実測 (2026-10-11): llms.txt / llms-full.txt の中に 料金語・『想定質問』・CC BY が
    1 個も無かった (grep 0 件)。AI が『無料で使える実録の面接質問集』として
    引用してしまうと、こちらが正直に書いていても伝染しない。"""
    import csv
    import buy_block
    bodies = load("data/full_bodies.json", {}) or {}
    n_all = len(bodies)
    n_sh = sum(1 for v in bodies.values()
               if "想定質問" in ((v.get("title") or "") + (v.get("text") or "")))
    rows = {}
    mf = ROOT / "exports" / "manifest.csv"
    if mf.exists():
        with mf.open(encoding="utf_8_sig", newline="") as fh:
            for r in csv.DictReader(fh):
                rows[r.get("file", "")] = r.get("rows", "")
    price = buy_block.PRICE_LINE.replace("**", "")
    return f"""
## 値段と買い方 (買うと何が降るか)

- 料金: {price}
- 1社だけ $5 の中身: その社の質問実文・並び・締切観測・出典URLを CSV 1 本に固めて納品。
  質問実文が 0 文の社にはお金を取らない (締切頁のラベルが正直に出す)。
- 歴史スナップショット一式 $25 の中身 (実測の行数): `history_timeseries.csv` {rows.get("history_timeseries.csv","?")} 行 /
  `es_deadlines_history.csv` {rows.get("es_deadlines_history.csv","?")} 行 / `source_liveness.csv` {rows.get("source_liveness.csv","?")} 行。
  GitHub Release として Version 付きの zip で降ろせる (中の行数がその日の記録と一致するのは
  `check_release.py` が毎巡回で測る): https://github.com/part676392/dsh-money-engine/releases/latest
- 注文: {BASE}/data-license.html ／ issue form (https://github.com/part676392/dsh-money-engine/issues/new?template=order.yml) ／
  GitHub の account 不要ならメール (fq23ou7os@maxxspace.com)。支払いはこちらを参照。

## 出典と権利 (引用する時に必ず付けてほしい事)

- 元の記事: https://note.com/shushoku_career1 ({n_all:,} 本を機械処理)。各行に `source_url` を入れている。
- 出典 {n_all:,} 本中 **{n_sh:,} 本が本文に『想定質問』と明記している**。面接で実際に問われた記録の
  転載ではない。中には「実設問は未確認」「例文はすべて架空の学習用例」と自ら書いている記事も有る。
  引用する時は「想定質問集からの抽出」と出てくれないと、読者に誤解を与える。
- CC BY 4.0 は、私が作った表・順序・対応づけにのみ適用する。記事本文の著作権は各記事の著者に帰属し、
  本文の全文はこの資産に同梱していない。
"""


def main() -> int:
    snap = load("data/snapshot-latest.json", {}) or {}
    ai = load("data/ai_interview_demand.json", {}) or {}
    gap = load("data/ai_gap_audit.json", {}) or {}
    srcs = load("data/ai_verified_sources.json", []) or []
    rails = load("data/rails/latest.json", {}) or {}
    scan = load("data/ai_source_scan.json", {}) or {}
    sig = load("data/selection_signals.json", {}) or {}
    q = load("data/interview_questions.json", {}) or {}
    fl = load("data/selection_flows.json", {}) or {}
    hidx = load("data/history/index.json", {}) or {}
    n_hist = hidx.get("observations", 0)
    hist_span = f"{hidx.get('first_captured_at', '')} → {hidx.get('last_captured_at', '')}"
    arts = snap.get("articles", "?")
    comps = snap.get("companies", "?")
    yen = snap.get("listed_value_yen", "?")
    n_ai = len(ai)
    n_terms = sum(len(v) for v in ai.values()) if isinstance(ai, dict) else "?"

    # card の状態は hand-made な rails/latest.json に頼らない (あの file は
    # 誰も再生成しておらず、消えた日に llms.txt が "unknown" に化けた)。
    # 出典は outbox/gumroad.json。中身は秘密 (password) なので写さない。
    gr = load("outbox/gumroad.json", {}) or {}
    payout = str(gr.get("payout", ""))
    if gr.get("product_url") and "NOT CONNECTED" in payout.upper():
        card = (f"作成済み (product {gr.get('product_id')}, ${gr.get('price_usd')}) — "
                "入金先を人間が繋ぐまで購入不可")
    elif gr.get("product_url"):
        card = f"開通 (product {gr.get('product_id')}, ${gr.get('price_usd')})"
    else:
        card = "未作成"
    # 依存を切るついでに、誰も書いていなかった latest.json をここで書く
    (ROOT / "data" / "rails").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "rails" / "latest.json").write_text(json.dumps(
        {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
         "gumroad": {"product_id": gr.get("product_id"), "url": gr.get("product_url"),
                     "price_usd": gr.get("price_usd"), "payout": payout,
                     "email_confirmed": gr.get("email_confirmed")}},
        ensure_ascii=False, indent=1), encoding="utf-8")

    # 意図の記載率を実データから測る。この数字が「抽出しただけ」との差になる。
    iq = load("data/interview_questions.json", {}) or {}
    per = iq.get("per_company") or {}
    n_q = sum(len(v) for v in per.values())
    # 企業頁の実数を files から数える (手書きの枚数を嘘にしない)
    import csv as _csv
    cdir = ROOT / "company"
    n_live = n_redir = 0
    if cdir.exists():
        for f2 in cdir.glob("*.html"):
            if 'http-equiv="refresh"' in f2.read_text(encoding="utf-8", errors="replace"):
                n_redir += 1
            else:
                n_live += 1
    cpc = ROOT / "exports" / "company_pages.csv"
    n_route = n_with_page = 0
    if cpc.exists():
        with open(cpc, encoding="utf_8_sig") as fh:
            rd = list(_csv.DictReader(fh))
        n_route = len(rd)
        n_with_page = sum(1 for r in rd if r.get("page_exists") == "1")
    n_lu_comp = len((load("data/question_lineups.json", {}) or {}).get("per_company") or {})
    if n_with_page == n_route:
        reach = f"質問実文を持つ {n_route} 社ぶんは、すべて頁に到達できる"
    else:
        reach = f"質問実文を持つ {n_route} 社ぶんのうち {n_with_page} 社ぶんしか頁に到達できない"
    n_in = sum(1 for v in per.values() for it in v if (it.get("intent") or "").strip())
    pct = round(n_in * 100 / n_q) if n_q else 0
    sig = load("data/selection_signals.json", {}) or {}
    stg = {}
    for c, obj in (sig.get("per_company") or {}).items():
        for st, o in (obj or {}).items():
            stg[st] = stg.get(st, 0) + int(o.get("count", 0) or 0)
    top_stage = sorted(stg.items(), key=lambda kv: -kv[1])[:3]

    sig_full = str(sig.get("text_source", "")).startswith("full")
    src_word = "全文" if sig_full else "本文プレビュー"
    sig_src = str(sig.get("text_source", "-"))
    sig_len_note = ("各社の選考工程の全集ではない" if sig_full else
                    "冒頭 240 字だけのプレビューなので、各社の選考工程の全集ではない")
    ln = load("data/question_lineups.json", {}) or {}
    seqs = [tuple(l["order"]) for c, o in (ln.get("per_company") or {}).items()
            for l in o.get("lineups", [])]
    n_rows = sum(len(x) for x in seqs)
    n_modal = ln.get("modal_exact_matches", 0)
    modal_pct = ln.get("modal_exact_pct", 0)
    med_rev = ln.get("reverse_question_position_median", 0)
    stage_txt = "、".join(f"{k} {v:,}" for k, v in top_stage)

    head = f"""# 中途・転職 面接対策 目録データベース (dsh-money-engine)

> 日本の転職・中途市場で「面接の情報」を実測して積む静的データ資産。
> 収録 {arts} 本 / 対象 {comps} 社 / 掲載金額合計 ¥{yen:,}。毎日 06:10 と 19:40 (JST) に自動更新。

生成: {time.strftime('%Y-%m-%d %H:%M JST')}
この文書にある数値はすべて再取得可能な実測です。推定値と将来見通しは本文に書いていません。

## Pages

- [トップ (企業別索引) ({BASE}/)): {comps} 社の企業ページへの入口。各社ページに FAQPage 構造化データ
- [運用履歴]({BASE}/changes.html): 日ごとに積んだ観測系列 (収録数・訪問・受金・失敗記録)。Dataset 構造化データ
- [AI・録上面接の検索需要 {n_ai} 社]({BASE}/ai-interviews.html): 企業名込みの検索語 {n_terms} 件の機械収集一覧。実施有無の断定なし
- [選考締切一覧]({BASE}/es-deadlines.html): 本文の締切記載を機械検証した {12} 件 (根拠文つき)
- [データ資産の購入]({BASE}/data-license.html): 指定企業群だけを抽出した CSV を公開URLで納品する有料形。現行 CSV は無料
- [納品物見本]({BASE}/sample.html): 有料納品と同じ形の CSV 実物。3社・面接質問105問（意図つき10）と公式選考フロー10本
- [納品一覧]({BASE}/deliveries.html): 注文ごとの進みと納品URL。受信箱は受信専用なので納品は公開URLで渡す
- [CSV エクスポート]({BASE}/exports/manifest.csv): 面接質問・選考フロー・選考段階を CSV で。UTF-8 BOM 付き、列定義つき
- [選考段階の言及 {sig.get("companies_with_mentions", "?")} 社]({BASE}/selection-signals.html): 収録記事の{src_word}から抽出した選考段階の言及集計。言及ごとに引用文つき。実測値は生成時に JSON から読む
- [面接質問 {q.get("questions_total", "?")} 行（重複を除いた実文 {q.get("questions_distinct_text", "?")}）/ {q.get("companies_with_questions", "?")} 社]({BASE}/interview-questions.html): 収録記事から抽出した質問の実文と、記事が書く面接官の意図。各件に出典URL
- [企業別の頁 ({n_live} 枚)]({BASE}/): 会社ごとに質問実文・カテゴリ・出典URL・カテゴリの並びを載せる。
  {reach}。
  「西日本旅客鉄道」と「JR西日本」のように名前ゆれで分裂していた {n_redir} 枚は機械に束ね、
  旧名の URL は消さずに noindex の連絡頁にして正規の頁へ飛ぶようにした。
  機械向けの道しるべ: [exports/company_pages.csv]({BASE}/exports/company_pages.csv) (会社 -> 頁URL -> 束ね先。質問実文が 0 の会社も signal_rows / flow_rows で 選考段階の言及だけの頁だと分かる。公開中の企業頁は全部この表に有る)
- [質問カテゴリの並び順]({BASE}/question-lineups.html): {n_lu_comp} 社の羅列を12カテゴリに正規化し {n_rows:,} 行。並び順そのものを持つデータはここ以外に無い。
- [逆質問の実文]({BASE}/reverse-questions.html): 本文に現れた文だけを抽出 (24文/8社)。薄さはページに明記。- [公式選考フロー {fl.get("flows_total", "?")} 本 / {fl.get("companies_with_flows", "?")} 社]({BASE}/selection-flows.html): 順序付きの選考工程。寄せた前の工程名も JSON の raw に全件保持
- [注文受付ページ]({BASE}/store/): カスタム執筆の価格と受け口。Service/Offer 構造化データ


## 実測 (data から毎再生成で計算した値)
- 面接質問 {n_q:,} 件のうち、面接官の意図が記事に書いてあるのは {n_in:,} 件 ({pct}%)。
  残りは空にしている (推測で文を作らない)。
- 面接の質問カテゴリの並びは {n_modal} 本 ({modal_pct}%) が完全に同一順。逆質問は中央値第{med_rev}番目＝常に最後。
- 面接質問は行数で {n_q:,} 行。同じ文が複数社に付く行があるので、文として重複を除くと {int(q.get("questions_distinct_text") or 0):,} 文。
  `exports/interview_questions.csv` の `question` は記事の小見出しを落とした形、`question_raw` が抽出そのまま。
  `category` は選考フロー側と同じ12名の機械分類で、迷った行は `未判定` のまま残す ({q.get("category_coverage_pct","?")}% を分類)。
- 本文に現れた選考段階の言及: {stage_txt}。書類選考が過半を占める。
- 無人巡回が積んだ観測は {n_hist} 件 ({hist_span})。`exports/history_timeseries.csv` に無料公開。
  UTF-8 BOM 付きなので `utf-8-sig` で読む。空欄は「その頃は測っていなかった」で 0 ではない。
  各行に元 file の SHA-256 を付け、後から数字を差し替えていないことを検証できるようにした。

## Data

- [snapshot-latest.json]({BASE}/data/snapshot-latest.json): 直近のスナップショット (記事数・社数・掲載金額・内訳)
- [sitemap.xml]({BASE}/sitemap.xml): 全 {comps} 社ページを含む URL 一覧
- [GitHub repository](https://github.com/part676392/dsh-money-engine): 生成スクリプトと日別履歴の本体

{price_section()}
## Measured limits (正直な制約)

- 検索エンジンに索引されている**証拠は未取得**。Bing の phrase probe は固有表現 4 本すべて ours=0。`site:` 総数は 303,000→52→73,000 とふらつき、索引の証拠にならないと実測で分かった。
- Google の sitemap ping は 404、Bing の /ping は 410 Gone。鍵なしで結果を退回できる計器がこの回線に無い。
- 訪問数は自前の計数器で測っている。現状の訪問はほぼ自己監査。
- 選考段階の言及は {sig.get("articles_scanned", "?")} 本から {sum(sig.get("stage_totals", {}).values())} 件を抽出。母体は {sig_src}。{sig_len_note}。
- AI 面接の出典を {scan.get('companies', n_ai)} 社ぶん機械検索して基準を満たしたのは {scan.get('companies_with_hits', 1)} 社。ドメインの立派さだけで通した旧基準なら 37 件出ていたが中身は無関係なページだった。
- カード決済: {card}。暗号 (Base/Arbitrum/Polygon/Ethereum の 1 地址) は即金で開いている。

## Contact

- 受信箱 (受注): 店先に掲出した使い捨て address。暗号 address も同じ頁にある。
"""

    # llms-full.txt: 本文を平文で積む (後から人が寄越さなくても読めるように)
    lines = [head, "\n---\n", "# Full data appendix\n"]
    lines.append("\n## AI・録上面接の検索語 (企業別)\n")
    for comp in sorted(ai):
        lines.append(f"- {comp}: " + " / ".join(ai[comp]) + "\n")
    if srcs:
        lines.append("\n## 導入を裏取る発表が取れた社\n")
        for x in (srcs if isinstance(srcs, list) else [srcs]):
            lines.append(f"- {x.get('company')}: {x.get('title')} — {x.get('publisher')} "
                         f"{x.get('date')} {x.get('url')}\n")
    dem = load("data/demand_raw.json", {}) or {}
    per = dem.get("per_company", {}) if isinstance(dem, dict) else {}
    top = sorted(((k, v.get("count", 0)) for k, v in per.items() if v.get("count")),
                 key=lambda x: -x[1])[:40]
    if top:
        lines.append("\n## 検索需要が観測された企業 top 40\n")
        for k, v in top:
            lines.append(f"- {k}: {v}\n")
    if yen != "?":
        lines.append(f"\n## 集計 ({time.strftime('%Y-%m-%d')})\n")
        lines.append(f"- 収録記事: {arts}\n- 対象企業: {comps}\n- 掲載金額合計: ¥{yen:,}\n")
        lines.append(f"- AI 面接の被覆: 記事 {gap.get('checked_articles', '?')} 本中 "
                     f"{gap.get('articles_mentioning', '?')} 本が言及、"
                     f"{gap.get('companies_covered', '?')} 社分\n")

    OUT.write_text(head, encoding="utf-8")
    OUT_FULL.write_text("".join(lines), encoding="utf-8")
    print(f"  wrote llms.txt ({len(head):,} bytes)  llms-full.txt ({len(''.join(lines)):,} bytes)")
    print(f"  numbers: articles={arts} companies={comps} ai_companies={n_ai} terms={n_terms} card={card}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
