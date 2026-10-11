#!/usr/bin/env python3
"""締切表の history 台帳 (毎巡回で積む)。

堀の理屈: 締切は公开情報だが、**いつ・どの記事にどう書かれていたか**は二次的にしか残らない。
note の記事は削除・有料化・文言変更されるので、その日のpullを積んでいる所は他に無い。
同じ理屈で corpus の history は既に積んでいる (data/history/runs.*.jsonl)。締切は零だった
(実測: 台帳も CSV も初出日の列も無い) ので、ここで作り直す。

 台帳   : data/history/deadlines.jsonl  (追記のみ / 1 行 = 1 巡回で見た 1 締切)
 面      : es-deadlines.html の行に 初出日 / 何回目か を出す
 export : exports/es_deadlines_history.csv
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
# 開発機と無人機が同じ台帳に追記すると、merge (-X theirs) で片側の行が飛ぶ。
# runs.dev.jsonl / runs.runner.jsonl で既にやっている通り、機械ごとに分けて読む時に畳む。
WHERE = "runner" if "dsh-runner" in str(ROOT) else "dev"
LEDGERS = [ROOT / "data" / "history" / ("deadlines.%s.jsonl" % WHERE)]
ALL_LEDGERS = [ROOT / "data" / "history" / f"deadlines.{w}.jsonl" for w in ("dev", "runner")]
LEDGER = LEDGERS[0]        # 互換 (追記先は自分の機械のものだけ)
PAGE_JSON = ROOT / "data" / "es_deadlines_page.json"
CSV_OUT = ROOT / "exports" / "es_deadlines_history.csv"
COLS = ["seen", "date", "firm", "days", "price", "url", "title", "evidence", "key", "machine"]


def today() -> dt.date:
    import os
    return dt.date.fromisoformat(os.environ["DSH_AS_OF"]) if os.environ.get("DSH_AS_OF") else dt.date.today()


def append(quiet: bool = False) -> dict:
    """今日の巡退回数を数え、面に出た行を追記する。同じ日は回数を上げるだけ。"""
    d = today().isoformat()
    rows = json.loads(PAGE_JSON.read_text(encoding="utf-8")).get("open", []) if PAGE_JSON.exists() else []
    seen_runs = {}
    for r in _lines(all_machines=False):        # 自分の機械の今日は何回目か
        seen_runs[r.get("seen")] = max(seen_runs.get(r.get("seen"), 0), int(r.get("run", 0)))
    nrun = seen_runs.get(d, 0) + 1
    fresh = []
    for r in rows:
        fresh.append({"seen": d, "run": nrun, "machine": WHERE, "date": r.get("date"), "firm": r.get("firm"),
                      "days": r.get("days"), "price": r.get("price") or 0, "url": r.get("url"),
                      "title": (r.get("title") or "")[:120],
                      "evidence": (r.get("evidence") or "")[:200], "key": r.get("key")})
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        for r in fresh:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    firsts = first_seen()
    stats = {"today": d, "run": nrun, "appended": len(fresh), "ledger_lines": ledger_count(),
             "days": len({r["seen"] for r in _lines()}), "firms": len({r["firm"] for r in fresh})}
    if not quiet:
        print(f"  締切台帳 : 今日 {stats['appended']} 行を追記 (第{nrun}回) / 台帳 {stats['ledger_lines']} 行"
              f" / 初出 {stats['days']} 日 / 社 {stats['firms']}")
    return stats


def _lines(all_machines: bool = True) -> list:
    """台帳を読む。面の 初出日・回数・CSV は両機械を畳んだものを使う (堀なので落とさない)。

    machine は各機械の台帳を追記した時に自分の名をを入れる。入っていない旧行
    (実測: 150 行すべて machine=None。setdefault を except 節の中に落としていた) は、
    どの file から読んだかで埋める。それを忘れると dev と runner の別観測が
    同じ鍵に潰れて回数が半分に減った (150 行 -> 75 行)。
    """
    out = []
    for f in (ALL_LEDGERS if all_machines else LEDGERS):
        if not f.exists():
            continue
        tag = f.stem.split(".")[-1]
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if not r.get("machine"):
                    r["machine"] = tag
                out.append(r)
    seen, ded = set(), []
    for r in out:
        # merge=union で同じ観測が 2 行になる事があるので読む側で畳む (A/B 実測の保護)
        k = (r.get("seen"), r.get("run"), r.get("url"), r.get("date"), r.get("machine"))
        if k in seen:
            continue
        seen.add(k)
        ded.append(r)
    return ded


def ledger_count() -> int:
    """両機械を畳んだ行数 (表示・護りはこっちを見る)。"""
    return len(_lines())


def first_seen() -> dict:
    """(url, 締切日) を初めて見た日。面の 初出日 列はここからしか取らない (捏造禁止)。"""
    out: dict = {}
    for r in _lines():
        k = (r.get("url"), r.get("date"))
        seen = r.get("seen")
        if not k[0] or not seen:
            continue
        if k not in out or seen < out[k]:
            out[k] = seen
    return out


def times_seen() -> dict:
    """(url, 締切日) を何回見たか。面の「何回目か」はここから取り、回数も台帳の実測。"""
    out: dict = {}
    for r in _lines():
        k = (r.get("url"), r.get("date"))
        out[k] = out.get(k, 0) + 1
    return out


def write_csv(quiet: bool = False) -> int:
    rows = _lines()
    if not rows:
        return 0
    rows.sort(key=lambda r: (str(r.get("seen")), str(r.get("date")), str(r.get("firm"))))
    # 畳まない: どの機械がいつ見たかが残っている方が堀なので、CSV は台帳の全行を出す。
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", encoding="utf_8_sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    if not quiet:
        print(f"  締切 CSV  : {CSV_OUT.name} {len(rows)} 行")
    return len(rows)


if __name__ == "__main__":
    append()
    write_csv()
