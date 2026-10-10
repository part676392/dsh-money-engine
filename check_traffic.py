#!/usr/bin/env python3
"""自分の访问数を、鍵なしで読戻しまでできる計器で測る.

 前段の実測で死んだ計器:
   Google /ping   -> 404 (endpoint 廃止)
   Bing  /ping    -> 410 Gone
   Bing SERP      -> 最初は使えるが数分で絞られ、daikin を返し始めた
   DuckDuckGo html-> challenge (bot壁) を返す。21 mentions は全部 query のエコーだった
   countapi.xyz   -> DNS 解決不能

 なので索引の"代理"を測るのはやめて、直接測れる访问を測る。
 pixel は img なので JS 不要。Bot も数える。自分の audit も数える。
 それは減算せず、事実として history に残す。
"""
from __future__ import annotations

import json
import re
import pathlib
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent
HIST = ROOT / "data" / "traffic"
BASE = "https://abacus.jasoncameron.dev"
KEYS = {"store": "store", "home": "home", "mini": "mini", "license": "license"}
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SITE = "https://part676392.github.io/dsh-money-engine"


def api(path: str) -> dict:
    try:
        r = subprocess.run(["curl", "-s", "--max-time", "15", f"{BASE}{path}"],
                           capture_output=True, text=True, timeout=20)
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:70]}


def esc_ref(s: object) -> str:
    return str(s if s is not None else "")


def get_count(key: str):
    """abacus から 1 鍵読む。取れなければ None (0 と区別する)。"""
    v = api("/get/dsh-money-engine/" + key).get("value")
    return v if isinstance(v, int) else None


def main() -> int:
    HIST.mkdir(parents=True, exist_ok=True)
    prev_f = HIST / "latest.json"
    prev = json.loads(prev_f.read_text(encoding="utf-8")) if prev_f.exists() else {}

    out = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "counters": {}}
    for label, key in KEYS.items():
        g = api(f"/get/dsh-money-engine/{key}")
        v = g.get("value")
        old = (prev.get("counters", {}).get(label) or {}).get("value")
        delta = (v - old) if (isinstance(v, int) and isinstance(old, int)) else None
        out["counters"][label] = {"value": v, "delta": delta, "key": key}
        arrow = "" if not delta else f"  ↑ +{delta}"
        print(f"  {label:6s} hits={v}{arrow}", flush=True)

    # 流入源: 外に出した URL に ?src=<key> を付けた。頁の JS が param を見て
    # src-<key> にも hit を置くので、どの面から human が来たかが分離できる。
    # 台帳は data/traffic_sources.json (そこに無い key は数えない)。
    try:
        reg = json.loads((ROOT / "data" / "traffic_sources.json").read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        reg = {"sources": []}
        print(f"  ★ 台帳が読めない: {str(e)[:60]}")
    src_total = 0
    for s in reg.get("sources", []):
        v = api(f"/get/dsh-money-engine/src-{s['key']}").get("value")
        v = 0 if v is None else v
        src_total += v
        out["counters"]["src-" + s["key"]] = {"value": v, "surface": s["surface"],
                                              "target": s.get("target")}
        flag = "" if s.get("tagged", True) else "  [未打直: URL に ?src= が無い]"
        out["counters"]["src-" + s["key"]]["tagged"] = bool(s.get("tagged", True))
        print(f"  流入 {s['key']:9s} hits={v}  ({s['surface']}){flag}", flush=True)
    print(f"  流入源つき合計: {src_total}", flush=True)

    print(f"\n  site: {SITE}/store/  (pixel は実在する img)")
    (HIST / "latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(HIST / f"{time.strftime('%Y-%m-%d-%H%M')}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # pixel が実際にページへ埋まっているか、生の HTML を見て確認する
    try:
        r = subprocess.run(["curl", "-s", "--max-time", "20", f"{SITE}/store/"],
                           capture_output=True, text=True, timeout=25)
        # JS が base と key を連結するので完全な列は page に出ない (2026-10-11)。
        embedded = ('/hit/dsh-money-engine/"' in r.stdout) and ('fetch(b+"store"' in r.stdout)
        srcjs = "src-" in r.stdout and "location.search.match" in r.stdout
        print(f"  pixel embedded in live store page: {embedded}  流入源の JS: {srcjs}")
        if not srcjs:
            print("  ★ live の頁に ?src= を読む JS が無い (流入源が測れない)")
    except Exception as e:  # noqa: BLE001
        print(f"  pixel check failed: {str(e)[:60]}")

    # JS を実際に走らせて発火先を見る。文字列照合は「有る」までで「叩く」を証明しない。
    # (実測: curl では計上されない = JS を実行するクライアントだけが計上される)
    # 参照元。?src= を付けない访问 (検索・SNS) の内訳を測る。
    # abacus に一覧 API は無いので既知 host を-data/traffic_referrers.json-で持つ。
    # 既知に無い分は ref-any との差で出る = 盲点を数字で持つ。
    try:
        reg = json.loads((ROOT / "data" / "traffic_referrers.json").read_text(encoding="utf-8"))
        cands = [h["key"] for h in reg.get("hosts") or []]
    except Exception as e:  # noqa: BLE001
        cands, reg = [], {}
        print(f"  referrer registry が読めない: {str(e)[:50]}")
    got = {}
    for h in cands:
        v = get_count("ref-" + h)
        if isinstance(v, int) and v > 0:
            got[h] = v
    anyv = get_count("ref-any")
    tot_any = anyv if isinstance(anyv, int) else 0
    known = sum(got.values())
    print(f"  参照元: 既知ヒット {len(got)} host / 計 {known} 件  ref-any={tot_any}  "
          f"盲点 (未登録 host) = {max(tot_any - known, 0)}")
    for h, v in sorted(got.items(), key=lambda x: -x[1]):
        nm = next((z.get("what", "") for z in (reg.get("hosts") or []) if z["key"] == h), "")
        print(f"      {h:26s} {v:>4}  {esc_ref(nm)}")

    import shutil as _sh
    node = _sh.which("node")
    tgt = {"question-lineups.html": "lineup", "store/": "store", "sample.html": "sample"}
    if node:
        ok = True
        for path, key in tgt.items():
            u = SITE.rstrip("/") + "/" + path
            r = subprocess.run(["curl", "-s", "--max-time", "30", "-A", UA, u],
                               capture_output=True, text=True, timeout=45)
            m = re.findall(r"<script>\(function\(\).*?</script>", r.stdout, re.S)
            if not m:
                print(f"    tracker exec {path:20s} ★ script が無い")
                ok = False
                continue
            js = m[0][len("<script>"):-len("</script>")]
            probe = "pr32" if "lineup" in key else "ghrepo"
            src = ("globalThis.__h=[];globalThis.fetch=function(u,o){globalThis.__h.push(String(u));"
                   "return {then(){},catch(){}};};globalThis.location={search:'?src=" + probe
                   + "',hostname:'part676392.github.io'};"
                   "globalThis.document={referrer:'https://github.com/part676392/dsh-money-engine'};\n"
                   + js + "\nconsole.log(JSON.stringify(globalThis.__h));\n")
            tmp = pathlib.Path("/tmp/_tracker_check.js")
            tmp.write_text(src, encoding="utf-8")
            rr = subprocess.run([node, str(tmp)], capture_output=True, text=True, timeout=45)
            try:
                hits = json.loads(rr.stdout.strip().splitlines()[-1])
            except Exception:  # noqa: BLE001
                hits = []
            want = [f"/hit/dsh-money-engine/{key}", f"/hit/dsh-money-engine/src-{probe}",
                    "/hit/dsh-money-engine/ref-github.com", "/hit/dsh-money-engine/ref-any"]
            good = all(any(w in g for g in hits) for w in want)
            ok = ok and good
            print(f"    tracker exec {path:20s} {'発火 OK' if good else '★ 発火せず'}  "
                  + str([g.split('/hit/dsh-money-engine/')[-1] for g in hits]))
        if not ok:
            print("  ★ tracker の発火が証明できない (頁か JS が壊れている)")
    else:
        print("    tracker exec        : node が無いので実行検査は省略")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
