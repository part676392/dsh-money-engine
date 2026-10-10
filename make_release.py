#!/usr/bin/env python3
"""データセットの日付つきスナップショットを GitHub Release に積む.

 なぜ: 目標の堀は「history が検証できること」。Pages の頁は上書きされるので
 ある日の数字を後から証明できない。Release は tag + asset で **その日の CSV が
 その形だった**ことを残す。後から偽装できない。

 条件: 中身 (記事数・質問数・フロー数・段階言及数) が変わるときだけ出す。
 同じ数字で連発すると archive が読みにくなるから。
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import subprocess
import time
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
EXPORTS = ROOT / "exports"
DATA = ROOT / "data"
DIST = ROOT / "dist"
STATE = ROOT / "data" / "rails" / "last_release.json"
REPO = "part676392/dsh-money-engine"

NEED = ["interview_questions.csv", "selection_flows.csv", "selection_signals.csv", "manifest.csv"]
JSONS = ["interview_questions.json", "selection_flows.json", "selection_signals.json",
         "snapshot-latest.json", "es_deadlines_strict.json", "ai_interview_demand.json"]


def counts() -> dict:
    def n(p, key):
        f = DATA / p
        if not f.exists():
            return 0
        try:
            return json.loads(f.read_text(encoding="utf-8")).get(key, 0)
        except Exception:
            return 0
    return {
        "articles": n("snapshot-latest.json", "articles"),
        "questions": n("interview_questions.json", "questions_total"),
        "question_companies": n("interview_questions.json", "companies_with_questions"),
        "flows": n("selection_flows.json", "flows_total"),
        "flow_companies": n("selection_flows.json", "companies_with_flows"),
        "signals": n("selection_signals.json", "companies_with_mentions"),
    }


def main(force: bool = False) -> int:
    c = counts()
    if not any(c.values()):
        print("  counts が全部 0: 抽出がまだ。release 見送り")
        return 1
    missing = [f for f in NEED if not (EXPORTS / f).exists()]
    if missing:
        print(f"  exports 不足: {missing} (make_exports.py を先に)")
        return 1

    fp = hashlib.sha1(json.dumps(c, sort_keys=True).encode()).hexdigest()[:10]
    prev = {}
    if STATE.exists():
        prev = json.loads(STATE.read_text(encoding="utf-8"))
    if prev.get("fingerprint") == fp and not force:
        print(f"  中身同じ (fp={fp}) なので見送り  前回: {prev.get('tag')}")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M")
    tag = f"snap-{stamp}"
    DIST.mkdir(exist_ok=True)
    zpath = DIST / f"{tag}.zip"
    rows = {}
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in NEED:
            z.write(EXPORTS / f, f"exports/{f}")
            rows[f] = sum(1 for _ in open(EXPORTS / f, encoding="utf_8_sig")) - 1
        for f in JSONS:
            if (DATA / f).exists():
                z.write(DATA / f, f"data/{f}")
        info = {"tag": tag, "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "counts": c, "csv_rows": rows, "fingerprint": fp,
                "source": "https://note.com/shushoku_career1",
                "license_scope": ("CC BY 4.0 は抽出した表・順序・対応づけにのみ適用。"
                                  "本文の著作権は note の各記事の著者に帰属する。"
                                  "記事本文は意図的に同梱していない。")}
        z.writestr("SNAPSHOT_INFO.json", json.dumps(info, ensure_ascii=False, indent=1))

    kb = zpath.stat().st_size / 1024
    notes = (f"スナップショット {stamp}\n\n"
             f"| 観測 | 値 |\n|---|---|\n"
             f"| 収録記事 | {c['articles']:,} |\n"
             f"| 面接質問の実文 | {c['questions']:,} 問 / {c['question_companies']} 社 |\n"
             f"| 公式選考フロー | {c['flows']} 本 / {c['flow_companies']} 社 |\n"
             f"| 選考段階の言及 | 企業 {c['signals']} 社 |\n"
             f"| CSV 行数 | " + ", ".join(f"{k}={v:,}" for k, v in rows.items()) + " |\n\n"
             f"同梱: exports/*.csv, data/*.json, SNAPSHOT_INFO.json\n"
             f"本文 (記事の全文) は意図的に同梱していません。著作権は各記事の著者に帰属します。\n"
             f"fingerprint={fp}")

    cmd = ["gh", "release", "create", tag, str(zpath), "--repo", REPO,
           "--title", f"{tag}: 記事 {c['articles']:,} / 質問 {c['questions']:,} / フロー {c['flows']}",
           "--notes", notes]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        print(f"  ★ release 失敗 rc={r.returncode}: {(r.stderr or r.stdout).strip()[:220]}")
        return 1
    url = (r.stdout or "").strip().split()[-1]
    print(f"  created {tag}  zip={kb:,.0f} KB")
    print(f"    {url}")

    # 確認: tag が本当に立つか asset が本当に降るか
    v = subprocess.run(["gh", "release", "view", tag, "--repo", REPO,
                        "--json", "tagName,assets,publishedAt",
                        "--jq", '.tagName + " assets=" + (.assets|length|tostring) + " at=" + (.publishedAt // "-")'],
                       capture_output=True, text=True, timeout=90)
    print(f"    read-back: {(v.stdout or v.stderr).strip()[:130]}")
    # gh release view --json assets には browser_download_url が無い (url/apiUrl だけ)。
    # REST の方から取らないと空になって確認が黙って素通りする。
    u = subprocess.run(["gh", "api", f"repos/{REPO}/releases/tags/{tag}",
                        "--jq", ".assets[0].browser_download_url"],
                       capture_output=True, text=True, timeout=90)
    dl = (u.stdout or "").strip()
    if not dl:
        print(f"    ★ asset URL が空: jq の欄名か asset を確認 ({(u.stderr or '').strip()[:90]})")
    else:
        # HEAD (-I) だと本文が 0 になり「降れた」証拠にならない。GET で字数を見る。
        h = subprocess.run(["curl", "-sL", "--max-time", "90", dl, "-o", "/dev/null",
                            "-w", "%{http_code} %{size_download}"],
                           capture_output=True, text=True, timeout=100)
        print(f"    asset 実取得: {h.stdout.strip()}")
    STATE.write_text(json.dumps({"tag": tag, "fingerprint": fp, "counts": c, "url": url,
                                 "asset": dl, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(force="--force" in sys.argv))
