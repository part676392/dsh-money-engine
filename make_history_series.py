#!/usr/bin/env python3
"""history (日時の積) を 1 枚の CSV と index JSON にまとめて出す。

理由: 「歴史スナップショット一式 $25」は品物なのに、買い手が中身を見る手段が無かった
(実測: exports に行列表は無く、data-license の Service に distribution も無かった)。
穴は埋めたうえで、SHA-256 で改ざん検知できる状態を先に見せる。
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import re
import time

ROOT = pathlib.Path(__file__).resolve().parent
HIST = ROOT / "data" / "history"
OUT_CSV = ROOT / "exports" / "history_timeseries.csv"
OUT_RUNS = ROOT / "exports" / "history_runs.csv"
OUT_JSON = ROOT / "data" / "history" / "index.json"

# 列の並びは「後から取り直せない順」。 acessible な量が後ろ。
COLS = [
    "captured_at", "location", "articles", "companies", "listed_value_yen",
    "questions", "questions_raw", "companies_with_questions", "flows", "signals",
    # 2026-10-11 に分けた語 (それ以前の行は空になる)
    "stage_mentions", "company_stage_pairs",
    "lineup_rows", "lineup_companies", "lineup_modal_pct",
    "reverse_quotes", "reverse_companies",
    "deadlines_open", "orders_real", "orders_rehearsal", "orders_closed", "delivered",
    "traffic_total", "traffic_home", "traffic_store", "traffic_license", "traffic_sample",
    "traffic_lineup", "traffic_reverse", "traffic_mini",
    "cash_usd", "cash_eth", "sha256_source",
]


def cell(v) -> str:
    """不明を 0 にしない。旧 format の行を 0 で埋めると減少が嘘になる (changes.html と同じ結論)。"""
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def load() -> list:
    out = []
    for fp in sorted(HIST.glob("*.json")):
        if fp.name == "index.json":
            continue
        raw = fp.read_bytes()
        try:
            d = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        d["_sha256"] = hashlib.sha256(raw).hexdigest()
        d["_file"] = fp.name
        out.append(d)
    out.sort(key=lambda d: str(d.get("captured_at") or ""))
    return out


def load_runs() -> list:
    """追記専用の背骨 (runs.<loc>.jsonl)。日付 file は同じ日の再実行で上書きするので、
    走った分はここに残す (実測: 4 回走っても日付 file は 3 個だった)。"""
    out = []
    for fp in sorted(HIST.glob("runs.*.jsonl")):
        loc = fp.stem.replace("runs.", "")
        for ln in fp.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            d["_file"] = fp.name
            d["_loc"] = loc
            out.append(d)
    out.sort(key=lambda d: str(d.get("captured_at") or ""))
    return out


def write_rows(rows: list, out: pathlib.Path, extra: str = "") -> int:
    out.parent.mkdir(exist_ok=True)
    cols = (["run_of"] if extra else []) + COLS
    with open(out, "w", encoding="utf_8_sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for d in rows:
            tr = d.get("traffic") or {}
            rec = {c: cell(d.get(c)) for c in COLS}
            for k in list(tr):
                key = "traffic_" + re.sub(r"[^a-z0-9]+", "_", str(k)).strip("_")
                if key in COLS:
                    rec[key] = cell(tr.get(k))
            rec["sha256_source"] = d.get("_sha256", "")
            if extra:
                rec["run_of"] = extra
            w.writerow([rec.get(c, "") for c in cols])
    return len(rows)


def main() -> int:
    rows = load()
    if not rows:
        print("  history がまだ無いので行列表を作らない")
        return 0

    OUT_CSV.parent.mkdir(exist_ok=True)
    write_rows(rows, OUT_CSV)

    runs = load_runs()
    n_runs = write_rows(runs, OUT_RUNS, extra="daily_or_run") if runs else 0

    n = len(rows)
    first = rows[0].get("captured_at")
    last = rows[-1].get("captured_at")
    OUT_JSON.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "observations": n, "first_captured_at": first, "last_captured_at": last,
        "runs_recorded": n_runs,
        "runs_csv": "exports/history_runs.csv" if n_runs else None,
        "grain_note": ("observations は 日付×場所 の 1 件 (同じ日の再実行は上書き)。"
                      "走った回数の-series は runs_csv に別粒度で置く。"),
        "columns": COLS,
        "csv": "exports/history_timeseries.csv",
        "note": ("不明のセルは空欄。0 を入れていない理由は changes.html と同じ "
                 "(旧 format と混ぜると嘘の減少になる)。sha256_source は各 file の SHA-256。"),
        "rows": [{c: cell(r.get(c)) for c in COLS} | {"_file": r.get("_file")} for r in rows],
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"  履歴行列表: {n} 観測 / {len(COLS)} 列 → {OUT_CSV.name}")
    print(f"    範囲: {first} → {last}")
    print(f"    実行背骨: {n_runs} 行 → {OUT_RUNS.name}"
          + ("" if n_runs else "  (runs.*.jsonl がまだ無い = 次回巡回から積める)"))
    q = [r.get("questions") for r in rows if r.get("questions") is not None]
    print(f"    questions を積んだ観測: {len(q)}/{n} 値: {q}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
