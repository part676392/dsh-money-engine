"""面の先頭 (h1 の直下) を作る: 収録実文の previews → 注文欄。

実測で分かった 2 つの故障:
  1) 注文欄が頁の一番下にしか無かった (index.html 145,446 字のうち 99% 目)
  2) 上部欄を差した後も、企業頁は h1 → 値段 → 実文 の順だった
     = 価値を読む前に \$5 が出た。人は値段より前に「中身が本物か」を見る。
そこで h1 の直下に [実文 3 例] + [注文欄] を 1 塊 (strip) として差し込む。
builders は頁を再生成するので、再生成の後に必ずこれを囀す (daily_loop に順序済み)。
money_check.cta_check が骨格を点検する (実文が注文欄より前に 3 例有るか)。
"""
from __future__ import annotations

import csv
import html
import pathlib
import re
import urllib.parse

import buy_block

ROOT = pathlib.Path(__file__).resolve().parent
CSV = ROOT / "exports" / "interview_questions.csv"

STRIP_START = "<!--buy-strip-->"
STRIP_END = "<!--/buy-strip-->"

# 骨格の許容 (割合で測ると <style> や JSON-LD の字数に食われて嘘を出すので距離で測る)
GAP_LIMIT = 3200          # </h1> から注文欄までの字数
H1_LIMIT = 1600           # 本文の先頭から h1 までの字数
REAL_MIN = 3              # 注文欄より前に見せる収録実文の最低数


def company_of(rel: str) -> str:
    """company/<社名>.html から社名を戻す (別名連絡頁は main で弾く)。"""
    if not rel.startswith("company/"):
        return ""
    return urllib.parse.unquote(pathlib.Path(rel).stem)


def rows_by_company() -> dict:
    """exports/interview_questions.csv を {社名: [(実文, カテゴリ), ...]} に。"""
    if not CSV.exists():
        return {}
    out = {}
    with CSV.open(encoding="utf_8_sig") as fh:
        for r in csv.DictReader(fh):
            comp = (r.get("company") or "").strip()
            q = (r.get("question") or "").strip()
            if comp and q:
                out.setdefault(comp, []).append((q, (r.get("category") or "").strip()))
    return out


def pick_company(rows: list) -> list:
    """1社から 3 例。カテゴリが被らない行を優先 (同じ質問型が並ぶと価値が伝わらない)。"""
    out, seen_cat = [], set()
    for q, cat in rows:
        if cat and cat in seen_cat:
            continue
        seen_cat.add(cat)
        out.append(q)
        if len(out) >= REAL_MIN:
            break
    if len(out) < REAL_MIN:
        for q, _c in rows:
            if q not in out:
                out.append(q)
            if len(out) >= REAL_MIN:
                break
    return out[:REAL_MIN]


def pick_spread(table: dict) -> list:
    """index など社名を絞らない頁用: 別の会社から 3 例 (並べ方は決定的にして再生成で揺らさない)。"""
    out, seen_comp = [], set()
    for comp in sorted(table):
        if comp in seen_comp or not table[comp]:
            continue
        seen_comp.add(comp)
        out.append((comp, table[comp][0][0]))
        if len(out) >= REAL_MIN:
            break
    return out


def shown(company: str, table: dict) -> tuple:
    """この頁の h1 直下に出す実文の組と同定用のラベル。
    実文の無い企業頁 (実測 16 頁) は他社 3 例を『よその実例』として見せる。"""
    rows = table.get(company, []) if company else []
    if company and rows:
        return "company", pick_company(rows)
    return "spread", [q for _c, q in pick_spread(table)]


def strip_html(company: str, table: dict) -> str:
    """h1 の直下に置く塊: 収録実文 → 注文欄。"""
    if company and table.get(company):
        qs = pick_company(table[company])
        head = f"収録実文 {len(qs)} 例（この会社の行から・出典URLつき）"
        items = "".join("<li>" + html.escape(q) + "</li>" for q in qs)
        who = ""
    else:
        kind, qs = shown(company, table)
        sp = pick_spread(table)
        lead = (f"この会社の質問実文はまだ収録していません。よその実例 {len(sp)} 例を置きます。"
                if company else f"収録実文 {len(sp)} 例（別の会社から・出典URLつき）")
        head = lead
        items = "".join("<li>" + html.escape(q) + "　<span style='color:#7a828c'>"
                        + html.escape(c) + "</span></li>" for c, q in sp)
        who = ""
    prev = ("<div style='margin:12px 0 0;padding:11px 13px;background:#f6f8fb;"
            "border:1px solid #dde3ea;border-radius:6px'>"
            "<p style='margin:0 0 7px;font-size:.82rem;color:#4b5563'>" + head +
            "　<a style='color:#2547c9' href='" +
            ("/dsh-money-engine/company/" + urllib.parse.quote(company) + ".html" if company
             else "/dsh-money-engine/interview-questions.html") +
            "'>全量を見る</a></p><ul style='margin:0;padding-left:1.2em;font-size:.95rem;line-height:1.6'>"
            + items + "</ul></div>")
    return STRIP_START + prev + buy_block.bar(company) + STRIP_END


def polish(quiet: bool = False) -> tuple:
    """全頁の h1 直下に strip を (再)設置。既にある物は作り直すので二重に積もらない。"""
    table = rows_by_company()
    touched, missing, skipped = [], [], []
    files = list(ROOT.glob("*.html")) + list((ROOT / "store").glob("*.html")) \
        + list((ROOT / "company").glob("*.html"))
    for f in files:
        rel = f.name if f.parent == ROOT else f.relative_to(ROOT).as_posix()
        h = f.read_text(encoding="utf-8", errors="replace")
        if 'http-equiv="refresh"' in h or "</h1>" not in h:
            skipped.append(rel)
            continue
        comp = company_of(rel)
        if comp and not table.get(comp) and not quiet:
            missing.append(rel)
        new_strip = strip_html(comp, table)
        i, j = h.find(STRIP_START), h.find(STRIP_END)
        if i >= 0 and j > i:
            h2 = h[:i] + new_strip + h[j + len(STRIP_END):]
        else:
            h1i = h.find("</h1>")
            h2 = h[:h1i + 5] + new_strip + h[h1i + 5:]
        if h2 != h:
            f.write_text(h2, encoding="utf-8")
            touched.append(rel)
    if not quiet:
        print(f"  h1 直下の塊        : 作り直し {len(touched)} 頁 / 対象外 {len(skipped)} 頁"
              + (f" / 実文の無い企業頁 {len(missing)} 頁" if missing else ""))
    return touched, skipped, missing


def visible_body(h: str) -> str:
    """CSS・JSON-LD を落とした『人間が読む本文』。"""
    b0 = h.find("<body")
    b0 = h.find(">", b0) + 1 if b0 >= 0 else (h.find("</head>") + 1)
    body = h[b0 if b0 > 0 else 0:]
    body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
    body = re.sub(r"<style.*?</style>", "", body, flags=re.S)
    return body


def plain(body: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)))


def audit(quiet: bool = False) -> list:
    """骨格を返す: (rel, h1→注文欄の距離, h1 の位置, 前に出ている実文数, 期待数)。"""
    table = rows_by_company()
    out = []
    files = list(ROOT.glob("*.html")) + list((ROOT / "store").glob("*.html")) \
        + list((ROOT / "company").glob("*.html"))
    for f in files:
        if f.name == "404.html":
            continue
        h = f.read_text(encoding="utf-8", errors="replace")
        if 'http-equiv="refresh"' in h:
            continue
        rel = f.name if f.parent == ROOT else f.relative_to(ROOT).as_posix()
        body = visible_body(h)
        h1 = body.find("</h1>")
        oc = body.find("template=order.yml", h1 + 1) if h1 >= 0 else -1
        gap = (oc - h1) if (h1 >= 0 and oc > h1) else None
        comp = company_of(rel)
        before = plain(body[:oc]) if oc > 0 else ""
        _kind, qs = shown(comp, table)
        n_real = sum(1 for q in qs if q in before)
        out.append((rel, gap, h1, n_real, len(qs)))
    if not quiet:
        low = [r for r in out if r[3] < r[4] or r[3] < min(REAL_MIN, r[4])]
        bad_gap = [r for r in out if r[1] is None or r[1] > GAP_LIMIT
                   or r[2] < 0 or r[2] > H1_LIMIT]
        print(f"  骨格の点検        : {len(out)} 頁 / 最大 h1+{max((r[1] or 0) for r in out)} 字"
              f" / 実文が足りない {len(low)} 頁 / 位置が足りない {len(bad_gap)} 頁")
        if (low + bad_gap)[:3]:
            print(f"    ★ 例: {[(b[0], b[1], b[3], b[4]) for b in (low + bad_gap)[:3]]}")
    return out


if __name__ == "__main__":
    polish()
    rows = audit()
    bad = [r for r in rows if r[1] is None or r[1] > GAP_LIMIT] \
        + [r for r in rows if r[2] < 0 or r[2] > H1_LIMIT] \
        + [r for r in rows if r[3] < min(REAL_MIN, r[4]) or r[3] < r[4]]
    for rel, gap, h1, n_real, want in rows[:3]:
        print(f"    {rel:34s} h1 @{h1:5d} / 注文欄 +{str(gap):>5s} 字 / 実文 {n_real}/{want} 例")
    if bad:
        print(f"  ★ 骨格が足りない {len(bad)} 頁: {[(b[0], b[1], b[3]) for b in bad[:3]]}")
        raise SystemExit(1)
    print(f"  h1 直下 全頁 OK ({len(rows)} 頁 / 実文 {REAL_MIN} 例を注文欄より前に)")
