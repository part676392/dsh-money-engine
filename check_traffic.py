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
# 頁が撃つ key を全部ここで数える。鍵を増やしてここへ載せないと、
# live で数字が伸びていても日报だけ黙る (company を一度取りこぼした実測)。
KEYS = {
    "store": "store", "home": "home", "mini": "mini", "license": "license",
    "lineup": "lineup", "company": "company", "sample": "sample",
    "order-click": "order-click", "404": "404", "reverse": "reverse", "changes": "changes", "deliveries": "deliveries", "ai": "ai",
}
# クローラ計数 (tracker_js.BOTS が単一の実装)。索引の受け取り側が沈んでいても、
# クローラが到達したかだけ先に測れる。
from tracker_js import BOT_KEYS as _BOT_KEYS  # noqa: E402

KEYS.update({k: k for k in _BOT_KEYS})
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SITE = "https://part676392.github.io/dsh-money-engine"


def api(path: str, tries: int = 3) -> dict:
    """読み取り失敗を 0 に化かさないために、失敗は error で返して 2 度引き直す。
    実測: 39 本を連打すると src-pr32 (live 5) が黙って 0 と記録されていた。"""
    last = {}
    for i in range(max(1, tries)):
        try:
            r = subprocess.run(["curl", "-s", "--max-time", "15", f"{BASE}{path}"],
                               capture_output=True, text=True, timeout=20)
            if r.stdout.strip():
                try:
                    d = json.loads(r.stdout)
                except ValueError:
                    last = {"error": "JSON で無い応答 " + r.stdout[:40].replace("\n", " ")}
                else:
                    if isinstance(d, dict) and "value" in d:
                        return d
                    last = d if isinstance(d, dict) else {"error": str(d)[:60]}
            else:
                last = {"error": f"空応答 (curl rc={r.returncode})"}
        except Exception as e:  # noqa: BLE001
            last = {"error": str(e)[:70]}
        err = str(last.get("error", ""))
        if "Key not found" in err:
            return last          # 未踏は本物なので引き直さない
        if i + 1 < tries:
            # 間借り先は quota を文章で返す ("Try again in 1.99s")。その秒数だけ待つ。
            m = re.search(r"Try again in ([0-9.]+)", err)
            wait = float(m.group(1)) + 1.5 if m else 1.5 + i
            time.sleep(min(wait, 12.0))
    return last


def esc_ref(s: object) -> str:
    return str(s if s is not None else "")


def get_count(key: str):
    """abacus から 1 鍵読む。取れなければ None (0 と区別する)。"""
    v = api("/get/dsh-money-engine/" + key).get("value")
    return v if isinstance(v, int) else None


SEARCH_HOSTS = ("www.google.com", "google.com", "www.google.co.jp", "www.bing.com", "bing.com",
                "duckduckgo.com", "lite.duckduckgo.com", "search.yahoo.co.jp", "www.baidu.com",
                "marginaliasearch.online", "www.marginalia.nu", "www.mojeek.com", "ecosia.org",
                "www.startpage.com", "search.brave.com", "yandex.com")


def index_evidence(counters: dict) -> dict:
    """索引の証を2系統で出す。 scraper 計器 (check_indexation) が死んでいても这里是能動的に待つ。
    (a) ref-<検索エンジン> : 索引されていないと referrer が立たない。決定的証。
    (b) bot-<engine>      : クローラが頁に到達した (索引の前提条件)。先に測れる方。
    """
    ref_hits = sorted(k for k, v in counters.items()
                      if k.startswith("ref-") and any(h in k[4:] for h in SEARCH_HOSTS)
                      and (v or {}).get("value"))
    bot_hits = sorted(k for k, v in counters.items()
                      if k.startswith("bot-") and k != "bot-any" and (v or {}).get("value"))
    if ref_hits:
        verdict = "索引された (referrer が証)"
    elif bot_hits:
        verdict = "クローラ到達済み (索引はこれから)"
    else:
        verdict = "不明 (クローラも検索 referrer も未取得)"
    return {"indexed_via": ref_hits, "crawler": bot_hits, "verdict": verdict}


def index_evidence_selftest() -> bool:
    """決め打ちの2ケースで verdict が逆転しないこと (計器の計器)。"""
    a = index_evidence({"ref-www.google.com": {"value": 3}, "bot-google": {"value": 1}})
    b = index_evidence({"home": {"value": 16}, "bot-google": {"value": 2}})
    c = index_evidence({"home": {"value": 16}, "bot-google": {"value": 0}})
    ok = (a["verdict"].startswith("索引された") and a["indexed_via"] == ["ref-www.google.com"]
          and b["verdict"].startswith("クローラ到達済み")
          and c["verdict"].startswith("不明"))
    print(f"    index evidence self-test: {'PASS' if ok else '★ FAIL'}  (3 ケース)")
    return ok


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
        out["counters"][label] = {"value": v, "delta": delta, "key": key,
                                  "read_error": g.get("error")}
        arrow = "" if not delta else f"  ↑ +{delta}"
        shown = v if isinstance(v, int) else "未取得"
        print(f"  {label:6s} hits={shown}{arrow}", flush=True)

    # 流入源: 外に出した URL に ?src=<key> を付けた。頁の JS が param を見て
    # src-<key> にも hit を置くので、どの面から human が来たかが分離できる。
    # 台帳は data/traffic_sources.json (そこに無い key は数えない)。
    try:
        reg = json.loads((ROOT / "data" / "traffic_sources.json").read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        reg = {"sources": []}
        print(f"  ★ 台帳が読めない: {str(e)[:60]}")
    retired = []
    src_total = 0
    n_unknown_src = []
    n_err_src = []
    for s in reg.get("sources", []):
        if s.get("retired"):          # 置き換えた面は数えない (雑音をやめる)
            retired.append(s["key"])
            continue
        g = api(f"/get/dsh-money-engine/src-{s['key']}")
        v = g.get("value")
        err = g.get("error")
        if isinstance(v, int):
            src_total += v
        out["counters"]["src-" + s["key"]] = {"value": v, "surface": s["surface"],
                                              "target": s.get("target"),
                                              "read_error": err}
        time.sleep(1.1)     # 連打で相手が黙る (実測: quota 1 分あたり)。間隔あけ
        flag = "" if s.get("tagged", True) else "  [未打直: URL に ?src= が無い]"
        out["counters"]["src-" + s["key"]]["tagged"] = bool(s.get("tagged", True))
        if v is None:
            n_unknown_src.append(s["key"])
        shown_s = v if isinstance(v, int) else "未取得"
        print(f"  流入 {s['key']:9s} hits={shown_s}  ({s['surface']}){flag}", flush=True)
    print(f"  流入源つき合計: {src_total}", flush=True)
    if retired:
        print(f"  退役済み (数えない): {retired}", flush=True)

    # 台帳 (high water mark)。abacus の鍵は増える一方なので、減った = 鍵が作り直された意味。
    # 読み取り失敗 (value 無し) は台帳に書かない。失敗を 0 と混ぜるのが元の故障だった。
    led_f = HIST / "ledger.json"
    led = json.loads(led_f.read_text(encoding="utf-8")) if led_f.exists() else {}
    drops = []
    for k, rec in out["counters"].items():
        v = rec.get("value")
        if not isinstance(v, int):
            continue
        mx = (led.get(k) or {}).get("max")
        if isinstance(mx, int) and v < mx:
            drops.append(f"{k} {mx}→{v}")
        if not isinstance(mx, int) or v > mx:
            led[k] = {"max": v, "at": out["checked_at"]}
    led_f.write_text(json.dumps(led, ensure_ascii=False, indent=1), encoding="utf-8")
    never = [k for k, rec in out["counters"].items()
             if k.startswith("src-") and rec.get("read_error") == "Key not found"]
    failed = [k for k, rec in out["counters"].items()
              if k.startswith("src-") and rec.get("read_error") and rec["read_error"] != "Key not found"]
    print(f"  台帳: 記録 {len(led)} 鍵 / 面が一度も叩かれていない {len(never)} 鍵 / "
          f"読み取り失敗 {len(failed)} 鍵", flush=True)
    if drops:
        print(f"  ★ 鍵が減った (作り直された) {drops[:3]}  過去の流入は失われる", flush=True)
    if failed:
        print(f"  ★ 読み取り失敗 {failed[:3]}  (0 と混ぜないため未取得のまま)", flush=True)
    measure_bad = bool(drops or failed)

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
    # 台帳の変数を div 名で分ける。ここで reg を差し替えたせいで後段の topic 検査が
    # 違う dict を読んで黙って走らなかった (2026-10-11 実測: 検査行が出力に出ない)。
    try:
        rreg = json.loads((ROOT / "data" / "traffic_referrers.json").read_text(encoding="utf-8"))
        cands = [h["key"] for h in rreg.get("hosts") or []]
    except Exception as e:  # noqa: BLE001
        cands, rreg = [], {}
        print(f"  referrer registry が読めない: {str(e)[:50]}")
    got = {}
    for h in cands:
        v = get_count("ref-" + h)
        if isinstance(v, int) and v > 0:
            got[h] = v
    anyv = get_count("ref-any")
    # 「まだ誰も叩いていない (key が無い)」と「0 件」を混ぜない。
    # ref-any は今日入れたばかりなので、まだ key 自体が存在しない (HTTP 404)。
    tot_any = anyv if isinstance(anyv, int) else None
    known = sum(got.values())
    ev = index_evidence(out["counters"])
    craw = "、".join(ev["crawler"]) if ev["crawler"] else "未取得"
    refs = "、".join(ev["indexed_via"]) if ev["indexed_via"] else "未取得"
    print(f"  索引の手がかり : {ev['verdict']}  (クローラ: {craw} / 検索 referrer: {refs})")
    if not index_evidence_selftest():
        print("  ★ 索引の判定式が壊れている")
    print(f"  参照元: 既知ヒット {len(got)} host / 計 {known} 件  "
          f"ref-any={'未取得 (まだ叩かれていない)' if tot_any is None else tot_any}  "
          f"盲点 (未登録 host) = {'—' if tot_any is None else max(tot_any - known, 0)}")
    for h, v in sorted(got.items(), key=lambda x: -x[1]):
        nm = next((z.get("what", "") for z in (rreg.get("hosts") or []) if z["key"] == h), "")
        print(f"      {h:26s} {v:>4}  {esc_ref(nm)}")

    # ?src= を付けられない面 (GitHub topic 一覧) の検査。順位は star 依存で測れないので
    # 「連携が生きているか」だけを見る (topic を消された事故に気づくため)。
    disc = reg.get("discovery") or {}
    spots = disc.get("spot_check") or []
    if spots:
        miss = []
        for t in spots:
            r = subprocess.run(["gh", "api", "-X", "GET", "search/repositories",
                                "-f", f"q=topic:{t} user:part676392"],
                               capture_output=True, text=True, timeout=45)
            try:
                n = json.loads(r.stdout).get("total_count", 0)
            except Exception:  # noqa: BLE001
                n = -1
            if n < 1:
                miss.append(f"{t}={n}")
        print(f"  GitHub topic 連携 : {'OK' if not miss else '★ 検索に出ない ' + str(miss)}"
              f"  ({len(spots)}/{len(disc.get('github_topics') or [])} を抜き取り)")

    import shutil as _sh
    BOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    BOT_KEY = "bot-google"
    HUMAN_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
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

            # クローラの UA でも発火すること (索引の前提条件を先に測る計器)。
            bot_js = ("globalThis.__h=[];globalThis.fetch=function(u,o){globalThis.__h.push(String(u));"
                      "return {then(){},catch(){}};};globalThis.location={search:'',hostname:'x'};"
                      "globalThis.document={referrer:''};"
                      # node 26 では navigator が read-only。代入は黙って通らない (実測)。
                      "Object.defineProperty(globalThis,'navigator',{value:{userAgent:'"
                      + BOT_UA + "'},configurable:true,writable:true});\n" + js
                      + "\nconsole.log(JSON.stringify(globalThis.__h));\n")
            tmp.write_text(bot_js, encoding="utf-8")
            rb = subprocess.run([node, str(tmp)], capture_output=True, text=True, timeout=45)
            try:
                bh = [g.split("/hit/dsh-money-engine/")[-1] for g in json.loads(rb.stdout.strip().splitlines()[-1])]
            except Exception:  # noqa: BLE001
                bh = []
            bgood = BOT_KEY in bh and "bot-any" in bh
            ok = ok and bgood
            print(f"    tracker bot  {path:20s} {'発火 OK' if bgood else '★ 発火せず'}  {bh}")

            # 人間の UA では bot-* が鳴らないこと (二重計数の否定)。
            hum = bot_js.replace(BOT_UA, HUMAN_UA, 1)
            tmp.write_text(hum, encoding="utf-8")
            rh = subprocess.run([node, str(tmp)], capture_output=True, text=True, timeout=45)
            try:
                hh = [g.split("/hit/dsh-money-engine/")[-1] for g in json.loads(rh.stdout.strip().splitlines()[-1])]
            except Exception:  # noqa: BLE001
                hh = []
            hok = not [x for x in hh if x.startswith("bot-")]
            ok = ok and hok
            print(f"    tracker human{path:14s} {'bot なし OK' if hok else '★ bot が鳴った'}  {hh}")
        if not ok:
            print("  ★ tracker の発火が証明できない (頁か JS が壊れている)")
    else:
        print("    tracker exec        : node が無いので実行検査は省略")
    return 1 if measure_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
