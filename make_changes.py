#!/usr/bin/env python3
"""運用履歴を public なページにする.

 目的: 「蓄積した history が堀になる」は、溜めてだけで堀にならない。
 他人が後から作れないのは本文じゃなくて系列の長さなので、
 系列をそのまま見せる頁を毎晩再生成する。

 出典が確定している数値だけを出す:
   - data/history/YYYY-MM-DD.json  記事数・社数・掲載金額 (note 公開API由来)
   - data/traffic/*.json           访问計のread-back (abacus)
   - data/payments/*.json          暗号残高 (4 chain RPC)
   - data/distribution/*.json      配布面の生存
 推定・見込みは書かない。
"""
from __future__ import annotations

from tracker_js import tracker
import buy_block
BUY = buy_block.html()
import glob
import html
import json
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "changes.html"
SITE = "https://part676392.github.io/dsh-money-engine"


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def load(pattern: str) -> list:
    rows = []
    for f in sorted(glob.glob(str(ROOT / pattern))):
        try:
            rows.append((pathlib.Path(f).name, json.loads(pathlib.Path(f).read_text(encoding="utf-8"))))
        except Exception:  # noqa: BLE001
            continue
    return rows


def rows_daily() -> str:
    days = load("data/history/*.json")
    # dev/runner で分けたので file 名順と時刻順がズレる (実測: 05:55 の次に 05:44)。
    # 増減列は前行と比較するので時刻順に直さないと符号が嘘になる。
    days = sorted(days, key=lambda nd: str((nd[1] or {}).get("captured_at") or nd[0]))
    out = []
    prev = None

    def dl(now: int, was) -> str:
        """増減列。前は記事数しか見ておらず、访问や受注の伸びが見えていなかった (2026-10-11)。
        旧 format の行は鍵が無い = 0 ではなく不明。0 と混ぜると -1,779 の様な嘘の減少が出る。"""
        if was is None:
            return "—"
        w = int(was)
        if now > w:
            return f"+{now - w}"
        if now < w:
            return f"{now - w}"
        return "±0"

    def g(d: dict, k: str):
        v = d.get(k)
        return None if v is None else int(v)

    for name, d in days:
        art = int(d.get("articles") or 0)
        comp = int(d.get("companies") or 0)
        yen = int(d.get("listed_value_yen") or 0)
        qs, lu, tr = g(d, "questions"), g(d, "lineup_rows"), g(d, "traffic_total")
        ord_r, ord_h = g(d, "orders_real"), g(d, "orders_rehearsal")
        cells = (f"<tr><td>{esc(d.get('captured_at', name))}</td>"
                 f"<td>{esc(d.get('location', '?'))}</td>"
                 f"<td>{art}</td><td>{esc(dl(art, prev and g(prev, 'articles')))}</td>"
                 f"<td>{comp}</td>"
                 f"<td>{'—' if qs is None else format(qs, ',')}</td>"
                 f"<td>{esc(dl(qs if qs is not None else 0, prev and g(prev, 'questions')) if qs is not None else '—')}</td>"
                 f"<td>{'—' if lu is None else format(lu, ',')}</td>"
                 f"<td>{'—' if tr is None else tr}</td>"
                 f"<td>{'—' if ord_r is None else f'{ord_r} / {ord_h}'}</td>"
                 f"<td>{yen:,}</td></tr>")
        out.append(cells)
        prev = d
    if not out:
        return "<tr><td colspan=11>まだ履歴がありません</td></tr>"
    return "\n".join(out)


def rows_series(label: str, pattern: str, key: str, fmt: str = "{}") -> str:
    rows = []
    for name, d in load(pattern):
        v = d.get(key)
        if isinstance(v, dict):
            v = json.dumps(v, ensure_ascii=False)[:60]
        rows.append(f"<tr><td>{esc(name)}</td><td>{esc(fmt.format(v))}</td></tr>")
    if not rows:
        return f"<tr><td colspan=2>{esc(label)}: まだありません</td></tr>"
    return "\n".join(rows[-12:])


def rows_traffic() -> str:
    out = []
    for name, d in load("data/traffic/*.json"):
        c = d.get("counters", {}) or {}
        cells = " / ".join(f"{k}={v.get('value')}" for k, v in c.items())
        out.append(f"<tr><td>{esc(d.get('checked_at', name))}</td><td>{esc(cells)}</td></tr>")
    return "\n".join(out[-12:]) or '<tr><td colspan=2>まだありません</td></tr>'


def rows_pay() -> str:
    out = []
    for name, d in load("data/payments/*.json"):
        out.append(f"<tr><td>{esc(d.get('checked_at', name))}</td>"
                   f"<td>{esc(d.get('total_eth'))} ETH</td>"
                   f"<td>{esc(', '.join(d.get('incoming_on') or []) or '—')}</td></tr>")
    return "\n".join(out[-12:]) or '<tr><td colspan=3>まだありません</td></tr>'


def rows_ai_scan() -> str:
    """AI 面接の裏取りスキャン結果. 0 件なら 0 件と書くための行."""
    f = ROOT / "data" / "ai_source_scan.json"
    if not f.exists():
        return "まだ走査していません。"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return "ファイルはありますが読めません。"
    return (f"{d.get('scanned_at','?')} に {d.get('companies','?')} 社を走査、"
            f"基準を満たす出典が取れたのは <strong>{d.get('companies_with_hits','?')} 社</strong>"
            f"（基準: {esc(d.get('rule',''))}）。ドメインの立派さだけで通した旧基準なら "
            f"37 件出ていましたが、中身は商品サイトと株価ページでした。")


def main() -> None:
    days = load("data/history/*.json")
    n_days = len(days)
    today = time.strftime("%Y-%m-%d %H:%M JST")
    ld = {}
    lf = ROOT / "data" / "traffic" / "latest.json"
    if lf.exists():
        ld = json.loads(lf.read_text(encoding="utf-8")).get("counters", {})
    addr = ""
    wf = ROOT / "outbox" / "wallet.json"
    if wf.exists():
        addr = json.loads(wf.read_text(encoding="utf-8")).get("address", "")

    ld_json = json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "中途・転職 面接対策 目録 — 運用履歴",
        "description": ("日ごとに蓄積した観測系列: 収録記事数、対象社数、掲載金額、"
                        "访问数、受金残高、配布面の生存。後から再現できない実測のみ。"),
        "temporalCoverage": (f"{days[0][1].get('captured_at','')}/{days[-1][1].get('captured_at','')}"
                            if days else ""),
        "creator": {"@type": "Person", "name": "転職ナビ・中途キャリアの研究所"},
        "url": f"{SITE}/changes.html",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "creditText": "CC BY 4.0 は抽出した表・順序・対応づけにだけ適用します。本文の著作権は note の各記事の著者に帰属し、引用は出典URLつきで最小限に留めています。",
        "isBasedOn": "https://note.com/shushoku_career1",
    }, ensure_ascii=False, indent=1)

    doc = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>運用履歴 — 中途・転職 面接対策 目録</title>
<meta name="description" content="収録記事数・対象社数・掲載金額・访问・受金を日ごとに積んだ公開ログ。{n_days}日分。">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{SITE}/changes.html">
<script type="application/ld+json">
{ld_json}
</script>
<style>
body{{font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif;margin:0;background:#f6f5f2;color:#1d1c1a;line-height:1.7}}
main{{max-width:900px;margin:0 auto;padding:30px 18px 70px}}
h1{{font-size:1.3rem;margin:0 0 4px}} .sub{{color:#6d675e;font-size:.86rem;margin:0 0 20px}}
h2{{font-size:.98rem;margin:26px 0 8px;border-bottom:1px solid #ddd8cf;padding-bottom:5px}}
table{{width:100%;border-collapse:collapse;font-size:.85rem}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #e6e1d8}}
th{{background:#efeee9;font-weight:600}}
code{{background:#eceae4;padding:2px 5px;border-radius:4px;font-size:.78rem;word-break:break-all}}
.note{{font-size:.8rem;color:#6d675e;margin-top:24px}}
a{{color:#7a5230}}
</style></head><body><main>
<h1>運用履歴</h1>
<p class="sub">この目録が何をいつ観測したか。<strong>{n_days} 日分</strong>。数値はすべて再取得可能な実測で、推定と見込みは載せていません。</p>

<h2>収録の推移（note 公開API）</h2>
<table><thead><tr><th>観測時刻</th><th>場所</th><th>記事数</th><th>増減</th><th>対象社数</th><th>面接質問</th><th>増減</th><th>並び行数</th><th>访问合計</th><th>受注 実/練習</th><th>掲載金額(円)</th></tr></thead>
<tbody>
{rows_daily()}
</tbody></table>

<h2>访问（実ブラウザの計数、read-back 済み）</h2>
<table><thead><tr><th>確認時刻</th><th>ページ別</th></tr></thead><tbody>
{rows_traffic()}
</tbody></table>

<h2>受金（暗号・4 チーン RPC）</h2>
<p class="sub" style="margin:0 0 8px">受金口 <code>{esc(addr)}</code></p>
<table><thead><tr><th>確認時刻</th><th>合計</th><th>入金が動いた chains</th></tr></thead><tbody>
{rows_pay()}
</tbody></table>

<h2>監視している失敗</h2>
<p style="font-size:.86rem">この頁には成功だけを表示しない。壊れた計器は <a href="{SITE}/changes.html">同じ場所</a> に記録する。これまでに取り除いた誤検出：Bing の <code>site:</code> 総数を索引と誤読（固有表現 4 本すべて ours=0）、DuckDuckGo の 21 mentions が実際はクエリのエコー、<code>Y-R-U.github.io</code> の未展開テンプレート指摘は JS の中で正しく展開されていた、そして Gemini 回線が露骨な執筆を全面拒否していたことを製品公開後に見つけた。</p>

<h2>出典スキャンの実績</h2>
<p style="font-size:.86rem">{rows_ai_scan()}</p>

<p class="note">更新: {today}（毎晩 06:10 / 19:40 に自動再生成）／ 元データ: <code>data/history/</code>, <code>data/traffic/</code>, <code>data/payments/</code></p>
{tracker("changes")}{BUY}</main></body></html>"""
    OUT.write_text(doc, encoding="utf-8")
    print(f"  wrote changes.html ({len(doc):,} bytes)  days={n_days}  "
          f"traffic keys={list(ld.keys())}")


if __name__ == "__main__":
    main()
