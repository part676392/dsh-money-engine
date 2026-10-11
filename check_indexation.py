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
# 実測で応答しなくなった engine は「0 件」と「測れない」を混ぜないため退役させる。
# (mojeek は 403、lite.searx.be は HTTP 000 / 2026-10-11 10:44 実測)
RETIRED = {
    "mojeek": "403 (egress が弾かれている) — endpoint を探すまで数えない",
    "marginalia_lite": "lite.searx.be HTTP 000 (移転?) — 到達できる物を探す",
}

# 制御語: _refs が1つでも cite に出なければ、その engine は応答していない扱いにする
CONTROL = {"q": "DeepSeek Harness", "must_contain": ("deepseek",)}
MINE = [
    ("site 限定", f"site:{HOST}"),
    ("固有語 (誌名)", "After-Hours Spin Cycle"),
    ("固有語 (頁見出)", "中途・転職 面接対策 目録データベース"),
    ("企業×列", "大林組 選考フロー site:part676392.github.io"),
]


def fetch(url: str, tries: int = 2) -> tuple:
    """2 回まで引く。理由 2 つ:
    (a) curl が落ちると -o はファイルを更新しないので、前の応答が残って
        「失敗したのに結果があった」になる (実測で 000 なのに cites=2)。
    (b) DuckDuckGo は 202 を返して本文を薄くすることがある (実測 2026-10-11)。
        薄い応答をそのまま-controls にかけると「計器 dead」の偽計になる。
    """
    best = ("000 0", "")
    for i in range(max(1, tries)):
        tmp = pathlib.Path("/tmp/serp.html")
        if tmp.exists():
            tmp.unlink()
        r = subprocess.run(["curl", "-s", "--max-time", "25", "-A", UA,
                            "-H", "Accept-Language: en-US,en;q=0.9", url,
                            "-o", str(tmp), "-w", "%{http_code} %{size_download}"],
                           capture_output=True, text=True, timeout=35)
        body = tmp.read_text(encoding="utf-8", errors="replace") if tmp.exists() else ""
        st = r.stdout or "000 0"
        code = st.split()[0] if st.split() else "000"
        if code == "200" and len(body) > 4000:
            return st, body
        if len(body) > len(best[1]):
            best = (st, body)
        if i + 1 < tries:
            time.sleep(3)
    return best


def cites_of(h: str) -> list:
    out = [re.sub(r"<[^>]+>", "", c).strip().replace(" › ", "/")
           for c in re.findall(r"<cite[^>]*>(.*?)</cite>", h, re.S)]
    if not out:  # cite を使わない engine 向け
        urls = []
        for u in re.findall(r'href="((?:https?:)?//[^"]+)"', h):
            if u.startswith("//"):
                u = "https:" + u
            # DuckDuckGo は結果を //duckduckgo.com/l/?uddg=<encoded> に包む (実測)。
            # 包みを剥がさないと engine 自分の link しか数えず、制御が死んだように見えた。
            m = re.search(r"[?&]uddg=([^&]+)", u)
            if m:
                u = urllib.parse.unquote(m.group(1))
            urls.append(u)
        skip = ("duckduckgo.com", "searx", "mojeek.", "bing.com/search", "/search?")
        out = [u for u in urls if not any(x in u for x in skip)][:20]
    return out


def discovery_rail() -> bool:
    """発見の配管を通しているか。sitemap の全量を送らず一部だけ送っていた実測:
    sitemap 486 本 / IndexNow 送信 48 本 (根 8 + 需要 top 40)。438 枚が黙っていた。"""
    bad = []
    # 送信記録 (loop が書く) を先に読む。後で読むと (1b) が空で素通りした (制御で実測)。
    d_sent = {}
    _rec = ROOT / "data" / "rails" / "indexnow_latest.json"
    if _rec.exists():
        try:
            d_sent = json.loads(_rec.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            d_sent = {}
    smf = ROOT / "sitemap.xml"
    if not smf.exists():
        print("    発見の配管      : ★ sitemap.xml が無い")
        return False
    sm = smf.read_text(encoding="utf-8")
    urls = re.findall(r"<loc>(.*?)</loc>", sm)
    joined = "\n".join(urls)
    # (0) 実在する頁は全部 sitemap に乗せる (noindex と別名の連絡頁は送らない)。
    gap = []
    # sitemap は index を "…/" の形で載せるので、その形も許す (実測で誤検出 2 件)。
    rels = {urllib.parse.unquote(u.split("/dsh-money-engine/", 1)[-1]) for u in urls}
    for f in list(ROOT.glob("*.html")) + list((ROOT / "store").glob("*.html")):
        if f.name == "404.html":
            continue
        h = f.read_text(encoding="utf-8", errors="replace")
        if 'http-equiv="refresh"' in h or "noindex" in h:
            continue
        rel = f.name if f.parent == ROOT else f"store/{f.name}"
        alt = rel.replace("index.html", "")
        if rel not in rels and alt not in rels:
            gap.append(rel)
    if gap:
        bad.append(f"sitemap に実在頁が足りない {gap[:3]}")
    # (1) canonical な企業頁が全部入っているか
    miss = []
    for f in sorted((ROOT / "company").glob("*.html")):
        h = f.read_text(encoding="utf-8", errors="replace")
        if 'http-equiv="refresh"' in h:      # 別名の連絡頁 (noindex) は送らない
            continue
        if urllib.parse.quote(f.name) not in joined and f.name not in joined:
            miss.append(f.name[:-5][:16])
    if miss:
        bad.append(f"sitemap に企業頁が {len(miss)} 枚足りない {miss[:2]}")
    # (1b) 実際に送った URL に別名 (noindex) 頁が混ざっていないか
    sent = d_sent.get("urls") or []
    if sent:
        alias_sent = []
        for u in sent:
            if "/company/" not in u:
                continue
            name = urllib.parse.unquote(u.rstrip("/").split("/")[-1])
            f = ROOT / "company" / name
            if not f.exists():
                alias_sent.append(name[:18] + "(無い頁)")
                continue
            h = f.read_text(encoding="utf-8", errors="replace")
            if 'http-equiv="refresh"' in h or "noindex" in h:
                alias_sent.append(name[:18])
        if alias_sent:
            bad.append(f"別名頁を検索に送っている {alias_sent[:2]}")
    # (2) robots.txt が sitemap を示しているか
    rob = (ROOT / "robots.txt")
    if not rob.exists() or "sitemap.xml" not in rob.read_text(encoding="utf-8"):
        bad.append("robots.txt に Sitemap: 宣言が無い")
    # (3) 直近の送信実測が sitemap 全量を送ったか
    rec = ROOT / "data" / "rails" / "indexnow_latest.json"
    if rec.exists():
        d = json.loads(rec.read_text(encoding="utf-8"))
        d_sent = d
        sub, tot = int(d.get("submitted") or 0), max(len(urls), 1)
        sub_line = f"送信 {sub}/{tot} @{d.get('at','')}"
        # 鮮度: 巡回は日に2回走る。今日の送信記録が無い=送っていない (SyntaxError で
        # step が死んでいた実測がある 2026-10-11)。
        today = time.strftime("%Y-%m-%d")
        if not str(d.get("at", "")).startswith(today):
            bad.append(f"今日の送信記録が無い ({d.get('at','')})")
        if sub < tot * 0.9:
            bad.append(f"IndexNow 送信 {sub} / sitemap {tot} ({d.get('at','')})")
    else:
        sub_line = "送信記録 無し"
        bad.append("IndexNow の送信記録が無い (巡回が送ったか測れない)")
    # (4) key file が実際に取れるか (IndexNow はこれを取得的証明に使う)
    keyf = ROOT / "indexnow-key.txt"
    if keyf.exists():
        key = keyf.read_text(encoding="utf-8").strip()
        st, body = fetch(f"{BASE}/{key}.txt", tries=1)
        code = st.split()[0] if st.split() else "000"
        if code != "200" or key not in body:
            bad.append(f"key file が取れない HTTP {code}")
    ok = not bad
    print(f"    発見の配管      : {'OK' if ok else '★ ' + '; '.join(bad[:2])}"
          f"  (sitemap {len(urls)} 本・{sub_line}"
          + (f"・足りない頁 {len(gap)} 件" if gap else "") + ")")
    return ok


def main() -> int:
    print(f"  索引の実測 (制御実験つき) @ {time.strftime('%Y-%m-%d %H:%M:%S')}")
    rail_ok = discovery_rail()
    per_engine = {}
    any_indexed = False
    any_alive = False
    for name, tpl in ENGINES:
        if name in RETIRED:
            per_engine[name] = {"verdict": "RETIRED", "reason": RETIRED[name], "retired": True}
            print(f"    {name:15s} 退役済み (数えない): {RETIRED[name]}")
            continue
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
        print("  ★★ INDEXED — 外部から発見され")
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
    return 0 if rail_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
