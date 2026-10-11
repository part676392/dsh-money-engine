#!/usr/bin/env python3
"""ES 締切ページ生成.

 主データ: data/es_deadlines_strict.json (extract_deadlines.py が本文から根拠付きで抽出)
 無ければ note title の日付表記にフォールバック。誇張禁止: 根拠の無い行は出さない。
"""
from __future__ import annotations

import buy_block
from tracker_js import tracker
import make_deadlines_history as DH
import datetime as dt
import os
import html
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
# 締切一覧の日付は実日付で動かす (固定日にしていたと、巡回が積もるほど「時点」が嘘になる)。
# 再現テストは DSH_AS_OF=YYYY-MM-DD で日被せできる。
TODAY = dt.date.fromisoformat(os.environ["DSH_AS_OF"]) if os.environ.get("DSH_AS_OF") else dt.date.today()
BASE = "https://part676392.github.io/dsh-money-engine"


YEAR_OK = (2025, 2030)


def sane(iso: str) -> bool:
    """西暦の見当を点検。capture 群に 2000 を足さず 西暦 26 年として通した実測がある
    (days=-730503 で全行が過去扱いになり、開いている行が 0 になった)。"""
    try:
        y = int(iso[:4])
    except Exception:
        return False
    return YEAR_OK[0] <= y <= YEAR_OK[1]


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def from_strict():
    p = ROOT / "data" / "es_deadlines_strict.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    rows = []
    for r in d.get("open", []):
        try:
            days = (dt.date.fromisoformat(r["date"]) - TODAY).days
        except Exception:
            continue
        if days < 0 or not sane(r["date"]):
            continue
        rows.append(dict(r, days=days))
    rows.sort(key=lambda r: (r["days"], -(r.get("price") or 0)))
    passed = len(d.get("all", [])) - len(d.get("open", []))
    return rows, passed, "本文の締切記載を機械検証（根拠文つき）"


def from_wide():
    """extract_deadlines_wide.py の全 600 記事引き直し結果。evidence 付きだけ通す。"""
    p = ROOT / "data" / "es_deadlines_wide.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    rows, dropped = [], 0
    for r in d.get("open", []):
        try:
            days = (dt.date.fromisoformat(r["date"]) - TODAY).days
        except Exception:
            dropped += 1
            continue
        if days < 0 or not r.get("url") or not r.get("evidence") or not sane(r["date"]):
            dropped += 1
            continue
        rows.append(dict(r, days=days))
    if dropped:
        print("  ★ wide: url/evidence/日付が揃わない %d 行を落とした" % dropped)
    return rows


def merged():
    """strict (高精度) + wide (全面引き直し) を (url, 日付) で畳む。strict を優先する。"""
    rows = {}
    st = from_strict()
    src = []
    if st and st[0]:
        for r in st[0]:
            rows[(r.get("url"), r.get("date"))] = dict(r, src="strict")
        src.append("strict %d" % len(st[0]))
    w = from_wide()
    add = 0
    for r in w:
        k = (r.get("url"), r.get("date"))
        if k not in rows:
            rows[k] = dict(r, src="wide")
            add += 1
    src.append("wide %d (新規 %d)" % (len(w), add))
    out = sorted(rows.values(), key=lambda r: (r["days"], -(r.get("price") or 0)))
    passed = 0
    for f in ("es_deadlines_strict.json", "es_deadlines_wide.json"):
        p = ROOT / "data" / f
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            passed += max(0, len(d.get("all", [])) - len(d.get("open", [])))
    method = "全 600 記事の本文から締切語と日付の近接を機械抽出（根拠文つき・" + " / ".join(src) + "）"
    return out, passed, method


def from_titles():
    corpus = json.load(open(ROOT / "data" / "corpus_full.json", encoding="utf-8"))
    es = [n for n in corpus if "ES" in (n.get("name") or "")]
    pat = re.compile(r"(?:(\d{1,2})/(\d{1,2})\s*締切|締切\s*(\d{1,2})/(\d{1,2}))")
    rows, passed = [], 0
    for n in es:
        t = n.get("name") or ""
        m = pat.search(t)
        if not m:
            continue
        mo = int(m.group(1) or m.group(3))
        da = int(m.group(2) or m.group(4))
        try:
            d = dt.date(2026, mo, da)
        except ValueError:
            continue
        days = (d - TODAY).days
        if days < 0:
            passed += 1
            continue
        firm = re.sub(r"【[^】]*】", "", re.split(r"のES|ES、|ESは|ES例文", t)[0]).strip(" ・")[:24]
        rows.append({"firm": firm, "date": d.isoformat(), "days": days,
                     "price": n.get("price") or 0,
                     "url": "https://note.com/shushoku_career1/n/" + str(n.get("key")),
                     "title": t[:74], "evidence": ""})
    rows.sort(key=lambda r: (r["days"], -(r.get("price") or 0)))
    return rows, passed, "記事タイトルに明記された日付のみ"


def render(rows, passed, method):
    nearest = rows[0]["date"][5:].replace("-", "/") if rows else "-"
    n_free = sum(1 for r in rows if not r["price"])
    n_paid = len(rows) - n_free
    soon = sum(1 for r in rows if r["days"] <= 3)
    soon_free = sum(1 for r in rows if r["days"] <= 3 and not r["price"])
    nd = rows[0]["days"] if rows else "-"

    firsts = DH.first_seen()
    times = DH.times_seen()
    items = []
    for r in rows[:80]:
        badge = "🆓 無料" if not r["price"] else "¥%s" % format(r["price"], ",")
        if r["days"] <= 1:
            urg = "⚰ 明日"
        elif r["days"] <= 3:
            urg = "🔥 残り%d日" % r["days"]
        else:
            urg = "⏳ 残り%d日" % r["days"]
        ev = "<div class='ev'>「%s」</div>" % esc(r["evidence"][:62]) if r.get("evidence") else ""
        k = (r["url"], r["date"])
        fs = firsts.get(k)
        n = times.get(k, 0)
        if fs:
            seen = "初出 %s%s" % (fs[5:].replace("-", "/"), (" / %d回目" % n) if n > 1 else "")
        else:
            seen = "今日初出"
        items.append("<tr><td><b>%s</b></td><td>%s</td><td><a href='%s'>%s</a></td><td>%s</td>"
                     "<td class='t'>%s%s<span class='hs'>%s</span></td></tr>" % (
                         r["date"][5:].replace("-", "/"), urg, esc(r["url"]), esc(r["firm"]),
                         badge, esc(r["title"][:52]), ev, esc(seen)))

    # 見出しの語は実集合に合わせる。wide でコンサル以外が入るのに「コンサル一覧」と騙さない。
    k = re.compile(r"コンサル|ファーム|監査|アドバイザ|EY|PwC|デロイト|KPMG|アビーム|アーンスト|トーマツ|PwC")
    n_cons = sum(1 for r in rows if k.search((r.get("firm") or "") + " " + (r.get("title") or "")))
    share = n_cons / max(1, len(rows))
    label = "28卒 コンサル・ファーム ES 締切" if share >= 0.5 else "28卒 ES 締切"
    scope = ("%d 件（うちコンサル・ファーム %d 件）" % (len(rows), n_cons)) if share < 0.5 \
        else ("%d 件" % len(rows))
    ld = {"@context": "https://schema.org", "@type": "ItemList",
          "name": label + "一覧 " + TODAY.strftime("%Y年%m月"),
          "dateModified": TODAY.isoformat(), "numberOfItems": len(rows),
          "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": r["firm"], "url": r["url"]}
                              for i, r in enumerate(rows[:20])]}

    doc = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>【%(nearest)s締切】%(label)s一覧 %(today)s時点｜%(n)d件</title>
<meta name="description" content="28卒 ES の締切を日付順に %(scope)s。無料%(free)d本・有料%(paid)d本を紐付け。各締切は記事本文の記載を機械検証。">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="%(base)s/es-deadlines.html">
<script type="application/ld+json">%(ld)s</script>
<style>body{font-family:system-ui,"Hiragino Sans",sans-serif;margin:0;background:#f7f8fa;color:#1b1f24;line-height:1.6}
main{max-width:960px;margin:0 auto;padding:26px 16px 60px}h1{font-size:1.3rem;margin:0 0 4px}
table{width:100%%;border-collapse:collapse;background:#fff;border:1px solid #e3e7ed;border-radius:9px;font-size:.83rem;overflow:hidden}
th{background:#eef1f5;padding:9px;text-align:left}td{padding:8px 9px;border-top:1px solid #eceff3;vertical-align:top}
.t{color:#5a6472;font-size:.79rem}.hs{display:block;color:#3f7d5a;font-size:.72rem;margin-top:2px}.ev{color:#8a93a0;font-size:.72rem;margin-top:3px}
a{color:#1a5fd6}.sub{color:#5a6472;font-size:.86rem}
.box{background:#fff4f2;border-left:4px solid #d0452c;border-radius:8px;padding:12px 14px;margin:16px 0;font-size:.9rem}
.free{background:#f2f8f2;border-left:4px solid #3f9d3f;border-radius:8px;padding:11px 14px;margin:14px 0;font-size:.85rem}
@media(max-width:640px){.t{max-width:210px}}</style></head><body><main>
<h1>%(label)s一覧（%(today)s 時点・%(scope)s）</h1>
<p class="sub">%(method)s。締切が迫っている順。</p>
<div class="box"><b>最速の締切は %(nearest)s（残り %(nd)s 日）。</b>
3日以内が %(soon)d件、うち無料で読める書き方ガイドが %(soonfree)d件。下の表からそのまま飛べます。</div>
<table><thead><tr><th>締切</th><th>猶予</th><th>企業</th><th>資料</th><th>記事と根拠記載・初出</th></tr></thead>
<tbody>
%(rows)s
</tbody></table>
%(tracker)s
<div class="free">この表は %(hist_days)d 日ぶん蓄積しています (台帳は前回巡回までに %(hist_lines)d 行)。
毎巡回で「いつ・どの記事にどう書かれていたか」を追記しているので、記事が消えても引き直せます
(<a href="./exports/es_deadlines_history.csv">es_deadlines_history.csv</a>)。
過去締切 %(passed)d 件は除外。各締切日は記事本文の記載を機械抽出し、引用文を各行に併記しています。
一覧は自動生成・毎日更新。<a href="./">企業別の目錄データベース</a></div>
</main></body></html>""" % {
        "nearest": nearest, "today": TODAY.strftime("%Y-%m-%d"), "n": len(rows),
        "label": label, "scope": scope, "n_cons": n_cons,
        "free": n_free, "paid": n_paid, "base": BASE,
        "ld": json.dumps(ld, ensure_ascii=False), "method": method,
        "soon": soon, "soonfree": soon_free, "nd": nd,
        "rows": "\n".join(items), "passed": passed, "tracker": tracker("deadlines"),
        "hist_days": len(firsts) and len({v for v in firsts.values()}) or 0,
        "hist_lines": DH.ledger_count(),
    }
    (ROOT / "es-deadlines.html").write_text(doc, encoding="utf-8")
    buy_block.inject(ROOT / "es-deadlines.html")
    json.dump({"generated": TODAY.isoformat(), "method": method, "open": rows},
              open(ROOT / "data" / "es_deadlines_page.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("rendered: %d rows (free %d / paid %d) via %s" % (len(rows), n_free, n_paid, method))


def main():
    rows, passed, method = merged()
    if not rows:
        rows, passed, method = from_titles()
    render(rows, passed, method)
    # 面を出した後に台帳へ積む (面の 初出日 は前の巡回までの台帳からしか引かない)
    DH.append()
    DH.write_csv()


if __name__ == "__main__":
    main()
