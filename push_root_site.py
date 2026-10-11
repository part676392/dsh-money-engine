#!/usr/bin/env python3
"""host root (https://part676392.github.io/) を作り直す。

実測 (2026-10-12 00:35 以前): host root は 404 だった。GitHub Pages の project page でも
検索ロボットは host 直下の /robots.txt を読むので、 sitemap への道が host 側に無かった。
root を開いて robots.txt に Sitemap を書き、sitemap index から本sitemapへ繋ぐ。

IndexNow の鍵の置き場所はここでも測った (2026-10-12):
  keyLocation = /dsh-money-engine/<key>.txt  -> api.indexnow.org 200 / bing 200
  keyLocation = host 直下 (または鍵のみ)      -> 403 UserForbiddedToAccessSite
なので host 直下にも鍵を置くが、送信は project path のまま動かさない。
"""
from __future__ import annotations

import datetime
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SITE = pathlib.Path("/tmp/rootsite-dsh")
REPO = "part676392/part676392.github.io"
BASE = "https://part676392.github.io/dsh-money-engine"


def gh(args: list) -> tuple:
    r = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout, r.stderr


def manifest_counts() -> dict:
    import csv
    p = ROOT / "exports" / "manifest.csv"
    want = {"interview_questions.csv": "質問",
            "selection_signals.csv": "選考段階",
            "selection_flows.csv": "選考フロー",
            "company_pages.csv": "企業頁"}
    out = {}
    if not p.exists():
        return out
    for r in csv.DictReader(p.read_text(encoding="utf_8_sig").splitlines()):
        k = r.get("file")
        if k in want:
            out[want[k]] = int(str(r.get("rows") or 0).replace(",", ""))
    return out


def page_count() -> int:
    """public している企業頁の数。company_pages.csv の行数 (496) ではなく、
    sitemap に立っている /company/ の loc 数 (実測 473) を頁数として出す。"""
    import re
    sm = ROOT / "sitemap.xml"
    if not sm.exists():
        return 0
    return len(re.findall(r"<loc>[^<]*/company/[^<]*</loc>", sm.read_text(encoding="utf-8")))


def files() -> dict:
    key = (ROOT / "data" / "indexnow.key").read_text().strip()
    c = manifest_counts()
    nq = f"{c.get('質問', 0):,}"
    ns = f"{c.get('選考段階', 0):,}"
    np_ = f"{page_count():,}"
    today = datetime.date.today().isoformat()
    f = {
        f"{key}.txt": key + "\n",
        "robots.txt": (
            "User-agent: *\nAllow: /\n\n"
            f"Sitemap: {BASE}/sitemap.xml\n\n"
            "# 機械向けのご案内 (実測の数を平文で置いてある):\n"
            f"#   {BASE}/llms.txt\n"
            f"# 面接質問の資料本体: 頁 {np_} 枚 / 質問 {nq} 行 / 選考段階 {ns} 行\n"
            f"# この host root は 2026-10-12 に開いた (それまで /robots.txt は 404 だった)\n"),
        "sitemap.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            "  <sitemap>\n" f"    <loc>{BASE}/sitemap.xml</loc>\n"
            f"    <lastmod>{today}</lastmod>\n" "  </sitemap>\n" "</sitemapindex>\n"),
    }
    sys.path.insert(0, str(ROOT))
    from tracker_js import tracker  # 単一実装の訪問計 (自苑分離入り)
    f["index.html"] = (
        '<!doctype html>\n<html lang="ja"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f'<title>part676392 — 日本企業 面接質問の資料 (頁 {np_} 枚 / 質問 {nq} 行)</title>\n'
        f'<meta name="description" content="日本企業の面接質問を公開記事から拾って構造化した資料。'
        f'頁 {np_} 枚 / 質問 {nq} 行 / 選考段階の言及 {ns} 行。CSV と機械向け案内を公開しています。">\n'
        '<meta name="robots" content="noai, noimageai">\n</head>'
        '<body style="font-family:system-ui,-apple-system,\'Hiragino Sans\';max-width:38rem;'
        'margin:3rem auto;padding:0 1rem;line-height:1.75;color:#1c2733">\n'
        '<h1>part676392</h1>\n'
        '<p>日本企業の面接質問を、公開されている記事から拾って構造化した資料を置いています。'
        '載せている数はすべて実測です。</p>\n<ul>\n'
        f'<li><a href="{BASE}/">資料の入口 (質問 {nq} 行)</a></li>\n'
        f'<li><a href="{BASE}/interview-questions.html">面接質問の一覧 (意図つきの行あり)</a></li>\n'
        f'<li><a href="{BASE}/question-lineups.html">質問カテゴリの並び順 (467社)</a></li>\n'
        f'<li><a href="{BASE}/es-deadlines.html">ES 締切の履歴 (根拠文つき)</a></li>\n'
        f'<li><a href="{BASE}/exports/manifest.csv">CSV 一覧と行数</a></li>\n'
        f'<li><a href="{BASE}/llms.txt">機械向けのご案内 (llms.txt)</a></li>\n'
        f'<li><a href="{BASE}/store/">1社だけの抽出 $5 から</a></li>\n'
        '</ul>\n'
        '<p style="font-size:.85rem;color:#5b6570">収録は公開記事の引用で、各引用に URL を併記しています。'
        '抽出した表は CC BY 4.0。個別抽出の注文はこの帳簿の GitHub issue で受けます '
        '(巡回が自動で送金先を返します)。</p>\n'
        + tracker("root") + "\n</body></html>\n")
    return f


def main() -> int:
    if not (ROOT / "data" / "indexnow.key").exists():
        print("  host root 再生成 : ★ data/indexnow.key が無い")
        return 1
    fs = files()
    # gh repo view --json defaultBranch はこの gh で unsupported (実測: Unknown JSON field)
    rc, out, err = gh(["api", f"repos/{REPO}", "-q", ".default_branch"])
    if rc != 0:
        print(f"  host root 再生成 : ★ repo が無い/読めない {REPO} ({err[:70]})")
        return 1
    branch = (out or "main").strip() or "main"
    SITE.mkdir(parents=True, exist_ok=True)
    if not (SITE / ".git").exists():
        rc, o2, e2 = gh(["repo", "clone", REPO, str(SITE)])
        if rc != 0:
            print(f"  host root 再生成 : ★ clone 失敗 {e2[:80]}")
            return 1
    changed = []
    for name, body in fs.items():
        p = SITE / name
        if not p.exists() or p.read_text(encoding="utf-8") != body:
            p.write_text(body, encoding="utf-8")
            changed.append(name)
    if not changed:
        print(f"  host root 再生成 : OK 変化無し ({len(fs)} file を見比べ)"
              f"  (質問 {manifest_counts().get('質問', 0):,} 行 / 頁 {page_count():,} 枚)")
        return 0
    subprocess.run(["git", "-C", str(SITE), "add", "-A"], check=True)
    msg = "host root を買い直し: 実測の数を更新 " + ", ".join(changed)
    r = subprocess.run(["git", "-C", str(SITE), "-c", "user.name=part676392",
                        "-c", "user.email=72697109+part676392@users.noreply.github.com",
                        "commit", "-m", msg], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  host root 再生成 : ★ commit {r.stderr[:80]}")
        return 1
    p = subprocess.run(["git", "-C", str(SITE), "push"], capture_output=True, text=True)
    if p.returncode != 0:
        print(f"  host root 再生成 : ★ push {p.stderr[:90]}")
        return 1
    print(f"  host root 再生成 : OK 更新 {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
