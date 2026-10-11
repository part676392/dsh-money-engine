#!/usr/bin/env python3
"""データ資産の販売頁をつくる.

 背景: 目録 (Pages) と CSV は公開したが、**データ資産自体に価格が無かった**
 (2026-10-11 実測: 販売頁 0 個)。小説側だけ値札があった。買い手が払う先が
 無いと金は動かないので、値札を置く。

 納品の物理: この環境の受信箱は受信専用 (mail.tm は送信が 405)。だから
 「メールで送ります」とは書けない。**公開URLで渡す**のが正直な納品形なので
 そう書く。嘘の導線を置いて受注後に嘘をつくよりマシ。
"""
from __future__ import annotations

import csv
import html
import json
import pathlib
import buy_block
import time
import urllib.parse
from tracker_js import tracker

ROOT = pathlib.Path(__file__).resolve().parent
BASE = "https://part676392.github.io/dsh-money-engine"
OUT = ROOT / "data-license.html"
DATA = ROOT / "data"
EXPORTS = ROOT / "exports"

# 企業数で決まる料金 (作った実績: 抽出は機械工程なので人数ではなく社数で切る)
# 1社 $5 を先頭に足した: 冷たい流入にとって $15 は「合うか分からないものへの初回」としては
# まず1社ぶんだけ見てもらう入口 (実測で閲覧自体が薄いので、入口の値段は低い方が有利)。
TIER = [(1, 5), (50, 15), (150, 35), (100000, 60)]
HISTORY_USD = 25


def tier_label(t: int) -> str:
    return "1社だけ試す" if t == 1 else (
        "カスタム抽出 全社ぶん" if t >= 100000 else f"カスタム抽出 〜{t}社")




def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def load(p: pathlib.Path, default=None):
    if not p.exists():
        return {} if default is None else default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def csv_rows(name: str) -> int:
    f = EXPORTS / name
    if not f.exists():
        return 0
    with open(f, encoding="utf_8_sig", newline="") as h:
        return max(sum(1 for _ in csv.reader(h)) - 1, 0)


def main() -> int:
    snap = load(DATA / "snapshot-latest.json")
    q = load(DATA / "interview_questions.json")
    fl = load(DATA / "selection_flows.json")
    sg = load(DATA / "selection_signals.json")
    # 面に出している物は es_deadlines_page.json (strict に全 600 記事の wide を畳んだ物)。
    # strict だけ読んでいた為、締切頁が 15 件なのに商店の数字は 12 件 (少ない方) を出していた。
    dl = load(DATA / "es_deadlines_page.json") or load(DATA / "es_deadlines_strict.json")
    rel = load(DATA / "rails" / "last_release.json")
    wallet = load(ROOT / "outbox" / "wallet.json")
    mail = load(ROOT / "outbox" / "mailtm.json")
    addr = wallet.get("address", "")
    inbox = mail.get("address", "")

    arts = snap.get("articles", 0)
    comps = snap.get("companies", 0)
    nq = q.get("questions_total", 0)
    # 行と実文は別の数 (実測: 1,779 行 / 実文 1,173 / 最多の1文が 500 行)
    n_dist = q.get("questions_distinct_text", 0)
    import order_link
    buy_url = html.escape(order_link.url(plan=order_link.ENTRY_PLAN), quote=True)
    from tracker_js import beacon_js as _beacon
    buy_beacon = _beacon("order-click")
    nf = fl.get("flows_total", 0)
    nfc = fl.get("companies_with_flows", 0)
    ns = sg.get("companies_with_mentions", 0)
    # 注文を実際に押せる導線にする (実測: アドレスが平文で mailto も issue も無かった)。
    _subj = "データ購入の注文"
    _body = ("プラン: \n企業一覧または語彙・業種:\n\n---\n"
             "https://part676392.github.io/dsh-money-engine/data-license.html")
    order_mail = ("mailto:" + inbox + "?subject=" + urllib.parse.quote(_subj)
                  + "&body=" + urllib.parse.quote(_body)) if inbox else ""
    order_issue = ("https://github.com/part676392/dsh-money-engine/issues/new?template=order.yml"
                   "&labels=" + urllib.parse.quote("注文"))
    rows = {k: csv_rows(k) for k in ("interview_questions.csv", "selection_flows.csv",
                                     "selection_signals.csv", "question_lineups.csv",
                                     "reverse_questions.csv", "manifest.csv")}
    # es_deadlines_strict.json は {generated, method, open[], all[]} の形。
    # list だと思って len すると 0 を誤読する (実測でなった)。
    n_dead = len(dl.get("open") or []) if isinstance(dl, dict) else (len(dl) if dl else 0)

    # 履歴の個数と範囲は頁に書くので、データから読む (直書きは枯れる)。
    hist_rows = []
    for hp in sorted((DATA / "history").glob("*.json")):
        if hp.name == "index.json":
            continue
        try:
            hist_rows.append(json.loads(hp.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            pass
    hist_rows.sort(key=lambda d: str(d.get("captured_at") or ""))
    n_hist = len(hist_rows)
    hist_span = ""
    if hist_rows:
        hist_span = f"{hist_rows[0].get('captured_at')} → {hist_rows[-1].get('captured_at')}"

    offers = [{"@type": "Offer", "name": tier_label(t), "price": p,
               "priceCurrency": "USD", "category": "custom-extraction",
               "description": (f"{'1社だけ' if t == 1 else '指定した最大 ' + str(t) + ' 社ぶん'}を抽出して CSV で納品。"
                               "納品は公開URL (この環境は受信専用で外送信できないため)。")}
              for t, p in TIER]
    offers.append({"@type": "Offer", "name": "歴史スナップショット一式", "price": HISTORY_USD,
                   "priceCurrency": "USD", "category": "history-bundle",
                   "description": ("tag 付きで積んできた日付つき CSV 一式と、回数表の差分一覧。"
                                   "ある日の数字がその形だった証明になる。")})

    ld = json.dumps({
        "@context": "https://schema.org", "@type": "Service",
        "name": "収録記事データベースのカスタム抽出と履歴一式",
        "serviceType": "data-extraction",
        "description": (f"収録記事 {arts} 本から機械抽出した面接質問 {nq:,} 行（重複を除いた実文 {n_dist:,}）・"
                        f"公式選考フロー {nf} 本を、指定企業群について CSV で納品。"
                        "納品は公開URLで渡す（外送信できないため）。"),
        "url": f"{BASE}/data-license.html",
        "provider": {"@type": "Person", "name": "dsh-money-engine 運用者"},
        "areaServed": "JP",
        "offers": offers,
        # 品物の中身を機械が読める形に。歴史一式 ($25) には preview ファイルが無かった (実測)。
        "serviceOutput": {
            "@type": "Dataset",
            "name": "転職・面接 目録データの時系列",
            "description": ("無人巡回で毎日積んだ観測値の行列表。不明のセルは空欄 (0 を入れない)。"
                            "各行に元 file の SHA-256 を付ける。"),
            "temporalCoverage": hist_span,
            "measurementTechnique": "automatic daily extraction",
            "distribution": [
                {"@type": "DataDownload", "encodingFormat": "CSV",
                 "name": "履歴の時系列 (無料 preview)",
                 "contentUrl": f"{BASE}/exports/history_timeseries.csv"},
                {"@type": "DataDownload", "encodingFormat": "application/json",
                 "name": "履歴 index と SHA-256",
                 "contentUrl": f"{BASE}/data/history/index.json"},
                {"@type": "DataDownload", "encodingFormat": "CSV",
                 "name": "面接質問の実文",
                 "contentUrl": f"{BASE}/exports/interview_questions.csv"},
                {"@type": "DataDownload", "encodingFormat": "CSV",
                 "name": "質問カテゴリの並び順",
                 "contentUrl": f"{BASE}/exports/question_lineups.csv"},
            ],
        },
    }, ensure_ascii=False, indent=1)

    tier_rows = "\n".join(
        f"<tr><td>{esc(tier_label(t))}</td>"
        f"<td>${p}</td><td>"
        + ("まずは1社ぶん。質問実文・面接官の意図・選考フロー・段階言及を1社のCSVで。"
           "合う形かを確認してから上の段に進めます。" if t == 1 else
           "指定した企業群だけを抽出した CSV。"
           "質問実文・面接官の意図・選考フロー・段階言及から選んだ列")
        + "</td></tr>"
        for t, p in TIER) + (
        f"\n<tr><td>歴史スナップショット一式</td><td>${HISTORY_USD}</td>"
        f"<td>tag 付きで積んだ日付つき CSV 全部と、回数の差分一覧 "
        f"(最新: <code>{esc(rel.get('tag', '—'))}</code>)。<br>"
        f"今積んでいる観測 <b>{n_hist}</b> 件・範囲 {esc(hist_span) or '—'}。"
        f"形を見る: <a href='exports/history_timeseries.csv'>履歴の時系列 CSV</a> ／ "
        f"<a href='data/history/index.json'>index (SHA-256 付)</a></td></tr>")

    doc = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>データ資産の購入 — カスタム抽出と履歴一式 | 目録</title>
<meta name="description" content="収録記事 {arts} 本から機械抽出した面接質問 {nq:,} 行（実文 {n_dist:,}）・選考フロー {nf} 本を指定企業群で CSV 納品。納品は公開URL。">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{BASE}/data-license.html">
{tracker("license")}
<script type="application/ld+json">
{ld}
</script>
<style>
body{{font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif;margin:0;background:#f6f5f2;color:#1d1c1a;line-height:1.7}}
main{{max-width:880px;margin:0 auto;padding:32px 18px 70px}}
h1{{font-size:1.35rem;margin:0 0 6px}} .sub{{color:#6d675e;font-size:.88rem;margin:0 0 18px}}
table{{width:100%;border-collapse:collapse;font-size:.9rem;margin:8px 0 4px}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid #e6e1d8;vertical-align:top}}
th{{background:#efeee9}} .now{{background:#fff;border:1px solid #e6e1d8;border-radius:8px;padding:12px 15px;font-size:.88rem;margin:14px 0}}
code{{background:#efece6;padding:1px 5px;border-radius:4px;word-break:break-all}}
.free{{background:#eef6ee;border:1px solid #cfe3cf;border-radius:8px;padding:12px 15px;font-size:.88rem;margin:16px 0}}
.warn{{background:#fff6e8;border:1px solid #e7cf9f;border-radius:8px;padding:12px 15px;font-size:.86rem;margin:16px 0}}
a{{color:#7a5230}} .note{{font-size:.8rem;color:#6d675e;margin-top:26px}}
ol{{font-size:.9rem}} ol li{{margin:8px 0}}
</style></head><body><main>
<h1>データ資産の購入</h1>
<p class="sub">目録データベースの無料公開はそのままに、<b>指定した分だけ切り出して渡す</b>形に値札を付けました。</p>

<div class="now"><b>今はいくつ入っているか（自動更新）</b><br>
収録記事 <b>{arts:,}</b> 本 ／ 企業 <b>{comps}</b> 社 ／ 面接質問 <b>{nq:,}</b> 行（重複を除いた実文 <b>{n_dist:,}</b>）／
公式選考フロー <b>{nf}</b> 本（{nfc} 社）／ 選考段階の言及のある企業 <b>{ns}</b> 社 ／
機械検証済みの締切 <b>{n_dead}</b> 件<br>
CSV 行数: 面接質問 {rows['interview_questions.csv']:,} ／ 選考フロー {rows['selection_flows.csv']:,} ／
選考段階 {rows['selection_signals.csv']:,} ／ <b>質問カテゴリの並び {rows['question_lineups.csv']:,} 行</b> ／
逆質問の実文 {rows['reverse_questions.csv']} 文
</div>

<div class="free"><b>無料のまま</b>: 上の CSV はそのまま落として使えます（出典URLつき、UTF-8 BOM 付き）。
有料を頂くのは下の2つだけです。<br>
<a href="exports/interview_questions.csv">interview_questions.csv</a> ／
<a href="exports/selection_flows.csv">selection_flows.csv</a> ／
<a href="exports/selection_signals.csv">selection_signals.csv</a> ／
<a href="exports/question_lineups.csv">question_lineups.csv</a> ／
<a href="exports/reverse_questions.csv">reverse_questions.csv</a> ／
<a href="exports/manifest.csv">列の定義</a><br>
<b>中を見たい方へ</b>: <a href="sample.html">納品物見本（3社ぶん実物）</a> — paid 版と同じ CSV をそのまま載せています。<br>
<b>注文後</b>: 進みと納品URLは <a href="deliveries.html">納品一覧</a> に積みます。</div>

{buy_block.provenance_note()}

{buy_block.history_block()}

<h2 style="font-size:1rem;margin:22px 0 6px">料金</h2>
<table><thead><tr><th>品物</th><th>値段</th><th>中身</th></tr></thead><tbody>
{tier_rows}
</tbody></table>
<p style="margin:14px 0 0"><a href="{buy_url}" style="display:inline-block;background:#7a5230;color:#fff;
padding:9px 15px;border-radius:8px;text-decoration:none;font-weight:600"
onclick="{buy_beacon};return true">注文を開く（$5 から）</a>
<span style="font-size:.8rem;color:#6d675e"> 開いた form は「1社だけ試す ($5)」を選んだ状態になります。
企業名を書いて送るだけです。<b>注文には GitHub のアカウントがいります</b> (未ログインだと最初にログイン画面へ飛びます。
そのまま戻ってくるので、書きかけの内容は消えません)。</span></p>

<div class="warn"><b>納品のしかたを先に正直に書きます。</b>
ここの受信箱は受信だけで、こちらからメールを送れません。だから納品は
<b>公開URL</b> で渡します（作ったらこの頁の下に納品一覧として載せ、そのURLを連絡に使う）。
「メールで納品」と書いて届かないより、この方が確かなのでこうしました。</div>

<h2 style="font-size:1rem;margin:22px 0 6px">順序</h2>
<ol>
<li>必要企業の一覧（または語彙・業種）を送る —
  <a href="{order_mail}">メールで送る ({esc(inbox) or '受信箱の準備中'})</a> ／
  <a href="{order_issue}"><b>GitHub の注文フォームで送る</b></a>（公開・個人の連絡先は要りません。納品はこの issue のコメントに出します）。</li>
<li>上の料金のどれかを下のアドレスへ送金（Base / Arbitrum / Polygon / ETH）。</li>
<li>こちらで抽出して CSV を作り、この頁の納品一覧に公開URLを載せる。送金内容が一致していれば受け取れる。</li>
</ol>
<p style="font-size:.9rem">送金先: <code>{esc(addr) or '（ウォレット未設定）'}</code><br>
<span style="font-size:.82rem;color:#6d675e">受金の履歴: <a href="changes.html">運用履歴の受金系列</a> ／
保存庫: <a href="https://github.com/{esc('part676392/dsh-money-engine')}/releases">GitHub Releases</a></span></p>

<div class="warn"><b>権利の範囲</b>: 記事本文の著作権は note の各記事の著者に帰属します。
だから <b>本文は納品物に入れません</b>（2,072,200字を意図的に別置きにしている）。
納品するのは抽出した表・順序・対応づけと出典URLです。CC BY 4.0 が掛かるのもその抽出部分だけ。</div>

<p class="note">更新: {time.strftime('%Y-%m-%d %H:%M JST')}（毎日 06:10 / 19:40 に自動再生成、上の数字も自動）
　他の観測: <a href="interview-questions.html">面接質問の実文</a> ／
　<a href="selection-flows.html">公式選考フロー</a> ／ <a href="selection-signals.html">選考段階</a> ／
　<a href="changes.html">運用履歴</a></p>
</main></body></html>"""
    OUT.write_text(doc, encoding="utf-8")
    print(f"  wrote data-license.html ({len(doc):,} bytes)")
    print(f"  数字: 記事={arts} 企業={comps} 質問={nq} フロー={nf}({nfc}社) 段階={ns}社 締切={n_dead}")
    print(f"  料金: " + ", ".join(f"{tier_label(t) if t != 100000 else str(comps)+'社'}=${p}" for t, p in TIER)
          + f", 履歴一式=${HISTORY_USD}")
    print(f"  納品形: 公開URL (外送信不可) / 受信箱={inbox or 'なし'} / 送金先={'あり' if addr else 'なし'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
