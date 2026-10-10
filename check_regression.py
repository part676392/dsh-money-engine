#!/usr/bin/env python3
"""再生成が published を劣化させていないか守る.

 なぜ: 無人 runner を ~/Documents の外に置く (launchd の bash は TCC に
 「Operation not permitted」で弾かれる — 2026-10-11 実測、43回全部手動だった)。
 その runner に data/full_bodies.json が無いと、面接質問の頁が
 1,779 行 → 94 行に**縮んで push** される。縮んだことは日志に出ない。
 だから数の減少を機械で止める。
"""
from __future__ import annotations

import csv
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / "data"
EXP = ROOT / "exports"
STATE = DATA / "rails" / "published_latest.json"
TOL = 0.10  # 10% までの減少は許容 (収録記事の入れ替え等で多少減ることがある)


def current() -> dict:
    def j(p, key):
        f = DATA / p
        if not f.exists():
            return 0
        try:
            return json.loads(f.read_text(encoding="utf-8")).get(key, 0)
        except Exception:
            return 0
    out = {
        "articles": j("snapshot-latest.json", "articles"),
        "companies": j("snapshot-latest.json", "companies"),
        "questions": j("interview_questions.json", "questions_total"),
        "question_companies": j("interview_questions.json", "companies_with_questions"),
        "flows": j("selection_flows.json", "flows_total"),
        "signals_companies": j("selection_signals.json", "companies_with_mentions"),
    }
    f = DATA / "es_deadlines_strict.json"
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out["deadlines_open"] = len(d.get("open") or []) if isinstance(d, dict) else 0
        except Exception:
            out["deadlines_open"] = 0
    # CSV の行数も見る (頁は強いのに CSV だけ空になる事故があり得る)
    for name, key in (("interview_questions.csv", "csv_questions"),
                      ("selection_flows.csv", "csv_flows"),
                      ("selection_signals.csv", "csv_signals")):
        p = EXP / name
        n = 0
        if p.exists():
            with open(p, encoding="utf_8_sig", newline="") as h:
                n = max(sum(1 for _ in csv.reader(h)) - 1, 0)
        out[key] = n
    return out


def compare(cur: dict, base: dict) -> list:
    """base (前回 published) に比べて 10% 以上減った鍵を返す。"""
    bad = []
    for k, v in cur.items():
        b = base.get(k, 0)
        if not isinstance(b, (int, float)) or b <= 0:
            continue
        if v < b * (1 - TOL):
            bad.append((k, b, v))
    return bad


def run_selftest() -> int:
    ok = True
    base = {"articles": 600, "questions": 1873, "csv_questions": 1779, "flows": 56,
            "deadlines_open": 12, "signals_companies": 475, "companies": 491,
            "question_companies": 472, "csv_flows": 96, "csv_signals": 2021}
    same = dict(base)
    if compare(same, base):
        print("  self-test A (同じ数字) : FAIL 通るべき"); ok = False
    else:
        print("  self-test A (同じ数字) : PASS")
    shrunk = dict(base); shrunk["csv_questions"] = 94  # full_bodies 喪失の事故
    got = compare(shrunk, base)
    if got and got[0][0] == "csv_questions":
        print(f"  self-test B (1,779→94) : PASS {got[0][1]:,}→{got[0][2]} を検出")
    else:
        print("  self-test B (1,779→94) : FAIL 検出すべき"); ok = False
    grown = dict(base); grown["articles"] = 640; grown["questions"] = 2000
    if compare(grown, base):
        print("  self-test C (増加)     : FAIL 通るべき"); ok = False
    else:
        print("  self-test C (増加)     : PASS")
    tiny = dict(base); tiny["questions"] = 1700  # -9.2% (許容内)
    if compare(tiny, base):
        print("  self-test D (-9%)      : FAIL 許容内のはず"); ok = False
    else:
        print("  self-test D (-9%)      : PASS")
    big = dict(base); big["questions"] = 1600  # -14.6%
    if not compare(big, base):
        print("  self-test E (-15%)     : FAIL 検出すべき"); ok = False
    else:
        print("  self-test E (-15%)     : PASS")
    empty = dict(base); empty["csv_flows"] = 0
    if not any(k == "csv_flows" for k, _, _ in compare(empty, base)):
        print("  self-test F (CSV空)    : FAIL 検出すべき"); ok = False
    else:
        print("  self-test F (CSV空)    : PASS")
    print(f"\n  regression self-test: {'ALL PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return run_selftest()
    cur = current()
    if not STATE.exists():
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                     "counts": cur}, ensure_ascii=False, indent=1), encoding="utf-8")
        print("  regression: baseline を初めて書いた (基準なしなので通す)")
        for k, v in cur.items():
            print(f"    {k:20s} {v:,}")
        return 0
    base = json.loads(STATE.read_text(encoding="utf-8")).get("counts", {})
    bad = compare(cur, base)
    if "--update" in sys.argv:
        if bad:
            print(f"  regression: 減少中なので baseline 更新を見送る {bad}")
            return 1
        STATE.write_text(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                     "counts": cur}, ensure_ascii=False, indent=1), encoding="utf-8")
        print("  regression: baseline 更新")
        return 0
    if bad:
        for k, b, v in bad:
            pct = (v - b) / b * 100 if b else 0
            print(f"    ★ {k:20s} {b:,} → {v:,}  ({pct:+.1f}%)")
        print(f"\n  regression: FAIL  基準 {STATE.name} とcompare上、{len(bad)} 鍵が {TOL:.0%} 以上減少")
        return 1
    print(f"  regression: OK  {len(cur)} 鍵すべて基準内 (許容 {TOL:.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
