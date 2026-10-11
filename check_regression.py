#!/usr/bin/env python3
"""再生成が published を劣化させていないか守る.

 なぜ: 無人 runner を ~/Documents の外に置く (launchd の bash は TCC に
 「Operation not permitted」で弾かれる — 2026-10-11 実測、43回全部手動だった)。
 その runner に data/full_bodies.json が無いと、面接質問の頁が
 1,779 行 → 94 行に**縮んで push** される。縮んだことは日志に出ない。
 だから数の減少を機械で止める。
"""
from __future__ import annotations

import ast
import csv
import json
import pathlib
import re
import subprocess
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


def traffic_keys_registered() -> bool:
    """頁が撃つ tracking key を check_traffic.KEYS が全部数えているか。
    abacus に key 一覧の API が無いので、code 側から列挙する (実測: company を
    KEYS に載せず、live は伸びているのに日报が黙っていた)。"""
    import re as _re
    import check_traffic as CT
    used = set()
    for f in sorted(ROOT.glob("*.py")):
        t = f.read_text(encoding="utf-8", errors="replace")
        for m in _re.finditer(r"""tracker\(\s*["']([a-z0-9-]+)["']""", t):
            used.add(m.group(1))
        for m in _re.finditer(r"""beacon_js\(\s*["']([a-z0-9-]+)["']""", t):
            used.add(m.group(1))
    # tracker_js が撃つ bot-* も数えているか (UA 表を更新して登録を忘れる事故)。
    try:
        from tracker_js import BOT_KEYS as _BK
        used |= set(_BK)
    except Exception:  # noqa: BLE001
        pass
    missing = sorted(used - set(CT.KEYS))
    ok = not missing
    print(f"    traffic keys      : {'OK' if ok else '★ KEYS に無い key ' + str(missing)}"
          f"  (頁が発火 {len(used)} / 数えている {len(CT.KEYS)})")
    return ok


def syntax_sweep() -> bool:
    """全 .py と巡回 script の構文を一括点検。
    実測で、patch 中の SyntaxError を見落として壊れた file を push した
    (ast.parse を write の後に入れたせいで、検査される前に commit された)。"""
    bad = []
    n = 0
    for fp in sorted(ROOT.glob("*.py")):
        n += 1
        try:
            ast.parse(fp.read_text(encoding="utf-8"))
        except SyntaxError as e:
            bad.append(f"{fp.name}:{e.lineno}")
    sh = ROOT / "daily_loop.sh"
    if sh.exists():
        r = subprocess.run(["bash", "-n", str(sh)], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            bad.append("daily_loop.sh:" + (r.stderr.strip().split("\n")[0][:40] or "bash -n"))
    ok = not bad
    print(f"  syntax sweep      : {'OK' if ok else '★'}  {n} py + 1 sh / 壊れ {len(bad)}"
          + (f"  {bad[:4]}" if bad else ""))
    # daily_loop.sh の heredoc python も同じ扱いにする。bash -n は中身を見ないため、
    # IndexNow の python が SyntaxError で死んでも巡回は green と出た (2026-10-11 実測)。
    loop = ROOT / "daily_loop.sh"
    if loop.exists():
        import re as _r
        txt = loop.read_text(encoding="utf-8")
        # Association ではなく delimiter を握手にする (PY 以外にも漏れないように)。
        blocks = [m.group(2) for m in _r.finditer(
            r"<<-?[ \t]*'?(?P<d>PY|PY3|EOF|PYEOF)'?[ \t]*\n(?P<b>.*?)\n(?P=d)\n", txt, _r.S)]
        for n, b in enumerate(blocks, 1):
            try:
                compile(b, f"daily_loop.sh:heredoc#{n}", "exec")
            except SyntaxError as e:
                bad.append(f"daily_loop.sh heredoc#{n}:{e.lineno}:{e.msg}")
        hb = [x for x in bad if "heredoc" in x]
        print(f"  loop heredoc      : {'OK' if not hb else '★ ' + str(hb[:2])}"
              f"  ({len(blocks)} block)")
    return ok


def tracker_single_source() -> bool:
    """访问計 JS の実装は tracker_js.py 1個でなければならない。
    実測で 7 file が手書き複製していて、片方だけ直して live に旧 JS を流した。"""
    needle = "abacus" + ".jasoncameron.dev/hit"  # 分解しないとこの file 自身が自己一致する
    owners = [fp.name for fp in sorted(ROOT.glob("*.py"))
              if needle in fp.read_text(encoding="utf-8", errors="replace")]
    ok = owners == ["tracker_js.py"]
    print(f"  tracker source      : {'OK' if ok else '★ 複製がある'}  実装 {owners}")
    # 頁側にも同じ検査: tracker を持つ頁は例外なく参照元節を持つ
    pages, nopage, drift = 0, [], []
    from tracker_js import tracker as _tr
    for p in list(ROOT.glob("*.html")) + list((ROOT / "store").glob("*.html")):
        h = p.read_text(encoding="utf-8", errors="replace")
        if "<script>(function(){try{var b=" not in h:
            continue
        pages += 1
        if "document.referrer" not in h:
            nopage.append(p.name)
        # tracker_js が今吐く JS と 1 文字でも違えば複製。定数だけを共有して本文を
        # 手書きコピーした頁 (question-lineups / sample) が旧 JS で live に出た実測がある。
        for m in re.finditer(r"<script>\(function\(\)\{.*?</script>", h, re.S):
            # 頁には URL が変数 b に入っていて、鍵は fetch(b+"home" の形にしか現れない。
            mm = re.search(r'fetch\(b\+"([a-z0-9-]+)"', m.group(0))
            if not mm:
                drift.append(p.name + ":key?")
            elif m.group(0) != _tr(mm.group(1)):
                drift.append(f"{p.name}({mm.group(1)})")
    ok = ok and not nopage
    print(f"  referrer on pages   : {'OK' if not nopage else '★ 節が無い頁 ' + str(nopage[:4])}"
          f"  ({pages} 頁中)")
    ok = ok and not drift
    print(f"  tracker と一致      : {'OK' if not drift else '★ 頁に旧 JS ' + str(drift[:4])}"
          f"  ({pages} 頁中)")
    return ok


def run_spine() -> bool:
    """実行背骨 runs.<loc>.jsonl が読めて、CSV と行数が合うこと。
    日付 file は同じ日の再実行で上書きされる (実測: 4 回走っても 3 file)。"""
    files = sorted(ROOT.glob("data/history/runs.*.jsonl"))
    bad, total = [], 0
    for fp in files:
        for i, ln in enumerate(fp.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if not ln.strip():
                continue
            total += 1
            try:
                d = json.loads(ln)
                if "captured_at" not in d:
                    bad.append(f"{fp.name}:{i} captured_at 無し")
            except Exception:  # noqa: BLE001
                bad.append(f"{fp.name}:{i} JSON ではない")
    csvf = ROOT / "exports" / "history_runs.csv"
    def csv_rows() -> int:
        if not csvf.exists():
            return 0
        with open(csvf, encoding="utf_8_sig") as f:
            return max(sum(1 for _ in f) - 1, 0)

    rows = csv_rows()
    note = ""
    # exports/*.csv は merge=generated。再生成した行列表を pull が他側に戻すので、
    # pre-flight では jsonl (追記・merge 対象外) と行数が食い違う誤★が出た
    # (実測 2026-10-11: jsonl 4 / CSV 2 で push 見送り)。derived なので作り直して測る。
    if rows != total and not bad and files:
        subprocess.run([sys.executable, str(ROOT / "make_history_series.py")],
                       capture_output=True, text=True, timeout=120)
        rows = csv_rows()
        note = "  (作り直してから一致)" if rows == total else "  (作り直しても不一致)"
    ok = bool(files) and not bad and rows == total
    print(f"  run spine         : {'OK' if ok else '★'}  jsonl {total} 行 / CSV {rows} 行"
          f" / file {len(files)}" + (f"  壊れ {bad[:3]}" if bad else "") + note)
    return ok


def loop_coverage() -> bool:
    """builder (build_*/make_*) は必ず巡回から呼ばれていること。
    実測で build_store と build_mini が daily_loop に無く、店の頁だけ無人再生成されず
    価格・受信箱・tracker が枯れていた。"""
    loop = (ROOT / "daily_loop.sh").read_text(encoding="utf-8", errors="replace")
    builders = [p.name for p in sorted(ROOT.glob("*.py"))
                if p.name.startswith(("build_", "make_"))]
    out = [n for n in builders if n not in loop]
    ok = not out
    print(f"  loop coverage     : {'OK' if ok else '★ 巡回から呼ばれない builder ' + str(out)}"
          f"  ({len(builders)} builder 中)")
    return ok


def main() -> int:
    if "--selftest" in sys.argv:
        return run_selftest()
    if not syntax_sweep():
        return 1
    if not traffic_keys_registered():
        return 1
    if not tracker_single_source():
        return 1
    if not run_spine():
        return 1
    if not loop_coverage():
        return 1
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
    # 堀の形。history が 5 鍵へ逆戻りしても無音だった (2026-10-11 実測)。
    import glob as _g
    # file 名順だと runner (23:47 記法) が dev (07:25) より後ろに来て、照らす対象を間違える
    # (実測: 5 鍵の方を見て ★ になった)。最新観測 = captured_at 最大で見る。
    # index.json は導出した索引であって観測ではない (実測で旧 format と誤表示した)。
    hs = [str(f) for f in sorted((x for x in _g.glob(str(ROOT / "data" / "history" / "*.json"))
                                 if not str(x).endswith("index.json")),
                                 key=lambda x: str(json.loads(pathlib.Path(x).read_text(encoding="utf-8"))
                                                  .get("captured_at") or ""))]
    need = ("questions", "lineup_rows", "traffic", "traffic_total", "orders_real", "location")
    last_keys, missing = [], list(need)
    if hs:
        try:
            d = json.loads(pathlib.Path(hs[-1]).read_text(encoding="utf-8"))
            last_keys = [k for k in d]
            missing = [k for k in need if k not in d]
        except Exception as e:  # noqa: BLE001
            missing = need + [f"read:{str(e)[:24]}"]
    if missing:
        print(f"  history shape     : ★ 鍵が無い {missing}  (最新 file の鍵 {len(last_keys)} 個)")
        return 1
    thin = [pathlib.Path(x).name for x in hs
            if len(json.loads(pathlib.Path(x).read_text(encoding="utf-8"))) < len(need) + 10]
    print(f"  history shape     : OK  {len(last_keys)} 鍵 (堀の系列を積めている)"
          + (f"  ※ 旧 format {len(thin)} file: {thin}" if thin else ""))
    print(f"  regression: OK  {len(cur)} 鍵すべて基準内 (許容 {TOL:.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
