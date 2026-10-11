#!/usr/bin/env python3
"""GitHub Release の『歴史スナップショット一式』が、本当にその日の物かどうか中身まで測る.

Pages の頁は上書きされるので、release が唯一の『その日の形』の証。
実測 (2026-10-11): release は 6 個あったが asset は source archive だけで、
歴史 CSV も README も入っていなかった ($25 の品物が Version として存在しなかった)。
だから『作った』で終わらせず、降ろして中身の行数を数え直す。
"""
from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = "part676392/dsh-money-engine"
HIST = ["es_deadlines_history.csv", "history_timeseries.csv", "source_liveness.csv", "history_runs.csv"]
MAIL = "fq23ou7os@maxxspace.com"
CACHE = ROOT / "outbox" / "release_probe.zip"


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=180)


def latest() -> dict:
    """gh release view の name は title だったので tag が取れなかった (実測)。
    API を直接読んで tag_name / assets / body を取る。"""
    r = gh("api", f"repos/{REPO}/releases/latest")
    if r.returncode != 0:
        return {}
    try:
        d = json.loads(r.stdout)
    except Exception:  # noqa: BLE001
        return {}
    return {"tag": d.get("tag_name"), "url": d.get("html_url"), "body": d.get("body") or "",
            "assets": d.get("assets") or [], "publishedAt": d.get("published_at")}


def rows_of(raw: bytes) -> int:
    txt = raw.decode("utf_8-sig", "replace")
    return max(0, sum(1 for _ in csv.reader(io.StringIO(txt))) - 1)


def check(download: bool = True) -> bool:
    d = latest()
    tag = d.get("tag") or ""
    assets = d.get("assets") or []
    if not tag or not assets:
        print(f"  履歴 release    : ★ 最新 release が読めない (tag={tag!r} asset={len(assets)})")
        return False
    want = f"{tag}.zip"
    a = next((x for x in assets if x.get("name") == want), None)
    if a is None:
        print(f"  履歴 release    : ★ {want} が無い (有る物: {[x.get('name') for x in assets]})")
        return False

    body = d.get("body") or ""
    back = len(re.findall(r"[?&]src=release", body))
    if back < 1:
        print(f"  履歴 release    : ★ 販売元に戻る link が本文に無い (src=release {back} 本)")
        return False

    if not download:
        print(f"  履歴 release    : OK (tag {tag} / asset {a.get('size', 0):,}B / backlink {back} 本)")
        return True

    # API の asset は url がそのまま download URL (databaseId は api json に無いので None になっていた = 実測 404)。
    url = a.get("url") or a.get("browser_download_url")
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/octet-stream",
                                                  "User-Agent": "dsh-money-engine"})
        tok = gh("auth", "token").stdout.strip()
        if tok:
            req.add_header("Authorization", f"token {tok}")
        raw = urllib.request.urlopen(req, timeout=120).read()
    except Exception as e:  # noqa: BLE001
        print(f"  履歴 release    : ★ asset が降ろせない ({str(e)[:60]})")
        return False
    CACHE.write_bytes(raw)

    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except Exception as e:  # noqa: BLE001
        print(f"  履歴 release    : ★ zip が開けない ({str(e)[:60]})")
        return False
    names = set(z.namelist())
    miss = [f for f in HIST + ["manifest.csv"] if f"exports/{f}" not in names]
    if "README.txt" not in names:
        miss.append("README.txt")
    if "SNAPSHOT_INFO.json" not in names:
        miss.append("SNAPSHOT_INFO.json")
    if miss:
        print(f"  履歴 release    : ★ zip に無い: {miss}")
        return False

    info = json.loads(z.read("SNAPSHOT_INFO.json").decode("utf-8"))
    claimed = {**(info.get("history_rows") or {}), **(info.get("csv_rows") or {})}
    bad = []
    real = {}
    for f in HIST:
        n = rows_of(z.read(f"exports/{f}"))
        real[f] = n
        c = claimed.get(f)
        if c is None:
            bad.append(f"{f}: INFO に行数の記載が無い")
        elif int(c) != n:
            bad.append(f"{f}: INFO {c} / zip の実測 {n}")
    if bad:
        print("  履歴 release    : ★ その日の行数と zip の中身が違う " + " / ".join(bad[:3]))
        return False

    rd = z.read("README.txt").decode("utf-8", "replace")
    need_words = ["想定質問", "CC BY 4.0", MAIL, "issues/new?template=order.yml"]
    lack = [w for w in need_words if w not in rd]
    if lack:
        print("  履歴 release    : ★ README に要害の語が無い " + str(lack))
        return False

    if real.get("es_deadlines_history.csv", 0) < 100:
        print(f"  履歴 release    : ★ 締切の履歴が薄い ({real.get('es_deadlines_history.csv', 0)} 行)")
        return False

    print(f"  履歴 release    : OK (tag {tag} / {len(raw):,}B / 歴史 4 file の行数が INFO と一致"
          f" / backlink {back} 本)")
    print("    同梱の実測      : " + " / ".join(f"{k} {v:,} 行" for k, v in real.items()))
    return True


if __name__ == "__main__":
    ok = check(download="--fast" not in sys.argv)
    if not ok:
        print("★★★ GUARD FAIL: release — $25 の品物 (履歴一式) が Version として降ろせない / 中身が証と違う")
    sys.exit(0 if ok else 1)
