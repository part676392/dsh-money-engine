#!/usr/bin/env python3
"""索引されているかを、**制御実験つき**で測る.

 動機 (2026-10-11 の実測):
   従来の計器は Bing の SERP から organic 件数と ours 件数を出していた。
   実物を見たら organic=10 の中身は ——
     Q: site:part676392.github.io   → translate.google.com ×10
     Q: "After-Hours Spin Cycle"    → linkedin.com/in ×10
   つまり Bing は **該当ゼロのときに無関係な頁を10件埋めてくる**。
   だから "organic=10" を「10件索引された」と読むのは間違いだった。
   (ours=0 という結論自体は正しかったが、それは偶然正しい読みだった。)

 だから制御実験を必須にする:
   1. CONTROL: 確かに存在する語 (DeepSeek Harness) を叩く。
      deepseek.com が返らなければ **その engine は計器として死んでいる**。
   2. MINE: 自分の site: と固有語を叩く。
   3. 判定は三値: INDEXED / NOT INDEXED (制御が生きている時のみ) / ORACLE DEAD
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import time
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent
BASE = "https://part676392.github.io/dsh-money-engine"
HOST = "part676392.github.io"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

ENGINES = [
    ("bing", "https://www.bing.com/search?{q}&count=20&setlang=en"),
    ("mojeek", "https://www.mojeek.com/search?{q}"),
    ("ddg_html", "https://html.duckduckgo.com/html/?{q}"),
    ("marginalia_lite", "https://lite.searx.be/search?{q}&categories=general"),
]
# 制御語: _refs が1つでも cite に出なければ、その engine は応答していない扱いにする
CONTROL = {"q": "DeepSeek Harness", "must_contain": ("deepseek",)}
MINE = [
    ("site 限定", f"site:{HOST}"),
    ("固有語 (誌名)", "After-Hours Spin Cycle"),
    ("固有語 (頁見出)", "中途・転職 面接対策 目録データベース"),
    ("企業×列", "大林組 選考フロー site:part676392.github.io"),
]


def fetch(url: str) -> tuple:
    # curl が落ちると -o はファイルを更新しない。前の応答が残って
    # 「失敗したのに結果があった」ことになる (実測で 000 なのに cites=2)。
    tmp = pathlib.Path("/tmp/serp.html")
    if tmp.exists():
        tmp.unlink()
    r = subprocess.run(["curl", "-s", "--max-time", "25", "-A", UA,
                        "-H", "Accept-Language: en-US,en;q=0.9", url,
                        "-o", str(tmp), "-w", "%{http_code} %{size_download}"],
                       capture_output=True, text=True, timeout=35)
    if not tmp.exists():
        return (r.stdout or "000 0"), ""
    return r.stdout, tmp.read_text(encoding="utf-8", errors="replace")


def cites_of(h: str) -> list:
    out = [re.sub(r"<[^>]+>", "", c).strip().replace(" › ", "/")
           for c in re.findall(r"<cite[^>]*>(.*?)</cite>", h, re.S)]
    if not out:  # cite を使わない engine 向け
        out = [m for m in re.findall(r'href="(https?://[^"]+)"', h)
               if "ddg" not in m and "searx" not in m][:20]
    return out


def main() -> int:
    print(f"  索引の実測 (制御実験つき) @ {time.strftime('%Y-%m-%d %H:%M:%S')}")
    per_engine = {}
    any_indexed = False
    any_alive = False
    for name, tpl in ENGINES:
        # --- 1. 制御 ---
        cq = urllib.parse.urlencode({"q": CONTROL["q"]})
        st, h = fetch(tpl.format(q=cq))
        cc = cites_of(h)
        alive = any(k in " ".join(cc).lower() for k in CONTROL["must_contain"])
        blocked = bool(re.search(r"captcha|Are you a robot|unusual traffic|error", h, re.I))
        status = st.split()[0] if st.split() else "000"
        ctl_ok = "✓" if alive else "✗"
        print(f"    {name:15s} HTTP={status:3s} 制御 {ctl_ok} (cites={len(cc)}) "
              f"first={cc[0][:48] if cc else '—'}")
        if not alive:
            per_engine[name] = {"control": False, "http": status, "blocked": blocked,
                                "verdict": "ORACLE DEAD", "queries": {}}
            print(f"      ★ 制御が応答しない → この engine の 0 は測定不能の意味")
            continue
        any_alive = True
        qres = {}
        for label, q in MINE:
            qq = urllib.parse.urlencode({"q": q})
            st2, h2 = fetch(tpl.format(q=qq))
            c2 = cites_of(h2)
            ours = [c for c in c2 if HOST in c or "dsh-money-engine" in c]
            filler = bool(c2) and not ours
            qres[label] = {"query": q, "http": (st2.split()[0] if st2.split() else "000"),
                           "cites": len(c2), "ours": len(ours),
                           "ours_urls": ours[:3], "filler_only": filler}
            mark = "★ INDEXED" if ours else ("埋め草のみ (該当ゼロ)" if filler else "無応答")
            print(f"        {label:16s} cites={len(c2):2d} ours={len(ours)}  {mark}")
            for u in ours[:2]:
                print(f"            → {u[:84]}")
            if ours:
                any_indexed = True
        per_engine[name] = {"control": True, "http": status, "blocked": blocked,
                            "verdict": "INDEXED" if any(v["ours"] for v in qres.values())
                            else "NOT INDEXED",
                            "queries": qres}
        print(f"      verdict: {per_engine[name]['verdict']}")

    live = {k: v["verdict"] for k, v in per_engine.items()}
    print(f"\n  engines: {live}")
    if any_indexed:
        print("  ★★ INDEXED — 外部から发现自己")
    elif any_alive:
        print("  索引されてはいないが、計器は生きている (NOT INDEXED が正しい読値)")
    else:
        print("  ★ 計器が全滅: 索引能否はこの回線では測れない")
    out = ROOT / "data" / "indexation_latest.json"
    out.write_text(json.dumps({
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "control": CONTROL, "engines": per_engine,
        "indexed_anywhere": any_indexed, "oracle_alive": any_alive},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
