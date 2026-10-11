#!/usr/bin/env python3
"""GitHub プロフィール頁 (part676392/part676392) の データ資産 節を data から作る。

プロフィールは目録の顔なので、そこに古い数字が載ると全部の信用が落ちる。
手書きで 4 箇所ズレた実測 (2026-10-11):
  - 「491社ぶん」 -> 会社を束ねて 473 社
  - 「面接質問の実文 1,779 問」 -> 1,779 行 / 実文 1,173 文
  - 「段階への言及 2,021 件」 -> CSV は 2,021 行
  - 「実行背骨 6 行」 -> 26 行
だから这里是再生成する。他の節 (HTML 修正サービスの側) は 1 バイトも触らない。
"""
from __future__ import annotations

import base64
import csv
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
OWNER_REPO = "part676392/part676392"
SITE = "https://part676392.github.io/dsh-money-engine"
MARK = "## データ資産"
LOCAL = ROOT / "data" / "profile_readme.md"


def load(name: str, default=None):
    f = ROOT / name
    if not f.exists():
        return default
    return json.loads(f.read_text(encoding="utf-8"))


def gh(*args: str, stdin: str = ""):
    return subprocess.run(["gh", *args], capture_output=True, text=True,
                          input=stdin, timeout=90)


def csv_counts(name: str, intent_col: str = ""):
    """exports の CSV を実際に読んで数える (JSON の key 名で嘘を書かないため)。"""
    f = ROOT / "exports" / name
    if not f.exists():
        return {"rows": 0, "companies": 0, "intent": 0}
    with open(f, encoding="utf_8_sig") as fh:
        rows = list(csv.DictReader(fh))
    comp = {r.get("company", "") for r in rows if r.get("company")}
    intent = 0
    if intent_col and rows:
        intent = sum(1 for r in rows if (r.get(intent_col) or "").strip())
    return {"rows": len(rows), "companies": len(comp), "intent": intent}


def spine_lines():
    n = 0
    for f in sorted((ROOT / "data" / "history").glob("runs.*.jsonl")):
        n += len([l for l in f.read_text(encoding="utf-8").splitlines() if l.strip()])
    return n


def schedule_hours() -> str:
    """launchd に実際に入っている時刻を読み返す。文を硬く置いて古くなる位なら読む。"""
    import plistlib
    f = pathlib.Path.home() / "Library" / "LaunchAgents" / "com.dsh.money-engine.plist"
    try:
        d = plistlib.load(open(f, "rb"))
        got = sorted((int(x["Hour"]), int(x["Minute"])) for x in d.get("StartCalendarInterval", []))
        if got:
            return " / ".join("%02d:%02d" % hm for hm in got)
    except Exception as e:
        print(f"  ★ schedule が読めない ({type(e).__name__}) ので既定を書く")
    return "06:10 / 13:20 / 19:40"


def section() -> str:
    snap = load("data/snapshot-latest.json", {}) or {}
    q = load("data/interview_questions.json", {}) or {}
    ln = load("data/question_lineups.json", {}) or {}
    idx = load("data/history/index.json", {}) or {}
    sig = csv_counts("selection_signals.csv")
    lnu = csv_counts("question_lineups.csv")
    flw = csv_counts("selection_flows.csv")
    qcsv = csv_counts("interview_questions.csv", "interviewer_intent")
    n_comp = int(snap.get("companies") or 0)
    n_art = int(snap.get("articles") or 0)
    yen = int(snap.get("listed_yen_total") or snap.get("listed_total") or 0)
    total = int(q.get("questions_total") or 0)
    dist = int(q.get("questions_distinct_text") or 0)
    qcomp = int(q.get("companies_with_questions") or 0)
    rawq = int(q.get("questions_extracted_raw") or 0)
    unatt = int(q.get("questions_unattributed") or 0)
    cov = int(q.get("category_assigned") or 0)
    cov_pct = f"{cov * 100 // total}%" if total else "—"
    lu_rows, lu_comp = lnu["rows"], lnu["companies"]
    f_rows, f_comp = flw["rows"], flw["companies"]
    n_intent = qcsv["intent"]
    if qcsv["rows"] and total != qcsv["rows"]:
        print(f"  ★ questions JSON {total:,} 行と CSV {qcsv['rows']:,} 行が違う")
        return ""
    obs = int(idx.get("observations") or 0)
    spine = spine_lines()
    # 締切と history は data と台帳から実測 (written 文を硬化させない)
    dl = load("data/es_deadlines_page.json", {}) or {}
    dl_rows = dl.get("open") or []
    dl_comp = len({r.get("firm") for r in dl_rows})
    dl_days = sorted({r.get("date") for r in dl_rows if r.get("date")})
    hist_dl = sum(1 for f in (ROOT / "data" / "history").glob("deadlines.*.jsonl")
                  for l in f.read_text(encoding="utf-8").splitlines() if l.strip())
    hist_liv = 0
    live_f = ROOT / "data" / "history" / "source_liveness.jsonl"
    if live_f.exists():
        hist_liv = len([l for l in live_f.read_text(encoding="utf-8").splitlines() if l.strip()])
    hours = schedule_hours()

    def u(path: str) -> str:
        return f"{SITE}{path}?src=prof"

    lines = [
        MARK,
        "",
        "### 転職・新卒 選考対策 目録データベース",
        u("/"),
        "",
        f"{n_art}本の面接対策・ES資料を {n_comp}社ぶんの企業名で横断検索できる目録。実測:",
        "",
        f"- 面接質問 **{total:,} 行（重複を除いた実文 {dist:,} 文）**／{qcomp}社 — "
        f"抽出 {rawq:,} span のうち {unatt} は企業に帰属できないので別列に分離",
        f"- 面接官の意図が記事に書いてある行 **{n_intent:,}（{n_intent * 100 // total if total else 0}%）** — "
        f"無い欄は空のまま（推測で補わない）",
        f"- 質問カテゴリの並び順 **{lu_rows:,} 行**（{lu_comp}社）— 逆質問はほぼ常に最後（中央値 10番目）",
        f"- 公式選考フロー **{f_rows:,} 行**（{f_comp}社・工程順つき）、段階への言及 "
        f"**{sig['rows']:,} 行**（{sig['companies']}社・根拠文つき）",
        f"- 質問のカテゴリ分類 **{cov:,} 行（{cov_pct}）**",
        f"- 企業別の頁 **{n_comp} 枚**（別名で割れていた URLs は本体へ誘導） — "
        f"機械が辿る道: {u('/exports/company_pages.csv')}",
        (f"- ES 締切 **{len(dl_rows)} 件**（{dl_comp}社・{dl_days[0]}〜{dl_days[-1]}）— "
         f"抽出の根拠文つき: {u('/es-deadlines.html')}" if dl_rows else
         "- ES 締切は現在 0 件（機械抽出で日付が取れていない日は 0 と書く）"),
        f"- 質問カテゴリの並び順の頁: {u('/question-lineups.html')} ／ 店の頁: {u('/store/')}",
        f"- 巡回は **毎日 {hours} JST** に自動で走り、取得日を `data/history/` に積む"
        f"（観測 {obs} 件・実行背骨 {spine} 行 / 締切台帳 {hist_dl:,} 行 / 出典の生存 {hist_liv:,} 行、各行に SHA-256）",
        "",
        f"機械可読: {u('/exports/manifest.csv')} ／ 締切の履歴: {u('/exports/es_deadlines_history.csv')} ／ 出典の生存: {u('/exports/source_liveness.csv')}",
        f"1社だけの抽出 **$5** から: {u('/data-license.html')}",
        f"CSV の中身を見る（3社ぶんの実物）: {u('/sample.html')}",
        f"企業の頁の実物: {u('/company/JR西日本（西日本旅客鉄道株式会社）.html')}",
        "",
        "記事の著作権は原作者に残す前提で、出典URLと引用1文までを公開しています（本文の再配布はしません）。",
        "派生表と正規化にのみ CC BY 4.0。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    r = gh("api", f"repos/{OWNER_REPO}/contents/README.md", "--jq", ".content")
    if r.returncode != 0:
        print(f"  ★ profile README が読めない: {r.stderr.strip()[:90]}")
        return 1
    cur = base64.b64decode(r.stdout.strip()).decode("utf-8")
    sha = gh("api", f"repos/{OWNER_REPO}/contents/README.md", "--jq", ".sha").stdout.strip()
    i = cur.find(MARK)
    head = (cur[:i].rstrip() + "\n") if i > 0 else (cur.rstrip() + "\n")
    new = head + "\n" + section()
    LOCAL.parent.mkdir(parents=True, exist_ok=True)
    LOCAL.write_text(new, encoding="utf-8")
    body_kept = (i < 0) or (head == cur[:i].rstrip() + "\n")
    if new == cur:
        print(f"  profile README は現状で一致 (変化なし / {len(new):,}字)")
        return 0
    payload = json.dumps({"message": f"データ資産の節を data から再生成 ({section().count('src=prof')} link)",
                          "content": base64.b64encode(new.encode("utf-8")).decode("ascii"),
                          "sha": sha}, ensure_ascii=False)
    put = gh("api", "-X", "PUT", f"repos/{OWNER_REPO}/contents/README.md", "--input", "-",
             stdin=payload)
    if put.returncode != 0:
        print(f"  ★ push 失敗: {put.stderr.strip()[:140]}")
        return 1
    print(f"  pushed profile README  {len(new):,}字  他の節は保持={body_kept}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
