#!/usr/bin/env python3
"""note の記事頁を直接取りに行って、本文を太く取り直す.

 発見 (2026-10-11 実測):
   note の公開API (corpus_full.json) の body は **全部ちょうど 240 字**。
   一方で記事の HTML 頁には同じ記事の本文が **3,000〜3,700 字** 載っていた
   (有料 ¥2,680 の記事でも同様)。つまりAPIだけ見ていた collections は
   使える本文の 7% しか見ていなかった。

 このスクリプトがやること:
   snapshot の URL を全部 GET して、本文要素のテキストだけを data/full_bodies.json
   に積む。全文を再発行はしない — 後で 引用 (1文) とリンクに使うための確保。
   note に負荷をかけないよう 0.55 秒/本。途中再開できる。
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
SNAP = ROOT / "data" / "snapshot-latest.json"
OUT = ROOT / "data" / "full_bodies.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
BODY_RE = re.compile(
    r'<div[^>]*class="[^"]*note-common-styles__text[^"]*"[^>]*>(.*?)</div>\s*</div>', re.S)
TAG = re.compile(r"<[^>]+>")


def slug_of(url: str) -> str:
    m = re.search(r"/n/([a-z0-9]+)", url or "")
    return m.group(1) if m else ""


def fetch_body(url: str, tries: int = 2) -> tuple:
    """(text, http_code). 取れなければ ("", code)."""
    for i in range(tries):
        try:
            r = subprocess.run(
                ["curl", "-sL", "--max-time", "35", "-A", UA, url,
                 "-o", "/tmp/note_article.html", "-w", "%{http_code}"],
                capture_output=True, text=True, timeout=45)
            code = r.stdout.strip()
        except Exception as e:  # noqa: BLE001
            time.sleep(2.0)
            continue
        if code != "200":
            time.sleep(1.5)
            continue
        html = pathlib.Path("/tmp/note_article.html").read_text(encoding="utf-8", errors="replace")
        m = BODY_RE.findall(html)
        if not m:
            return "", code
        # 最長ブロックが本文
        best = max(m, key=len)
        text = TAG.sub(" ", best)
        text = (text.replace("&gt;", ">").replace("&lt;", "<").replace("&quot;", '"')
                    .replace("&amp;", "&").replace("&nbsp;", " "))
        return re.sub(r"\s+", " ", text).strip(), code
    return "", "ERR"


def main() -> int:
    if not SNAP.exists():
        print("  snapshot が無い")
        return 1
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    have = {}
    if OUT.exists():
        try:
            have = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            have = {}
    recs = snap.get("records", [])
    todo = [r for r in recs
            if slug_of(r.get("url", "")) and len((have.get(slug_of(r["url"])) or {}).get("text", "")) < 800]
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if limit:
        todo = todo[:limit]
    print(f"  records={len(recs)}  取得済み={len(have)}  今回対象={len(todo)}")

    got = fail = 0
    lens = []
    started = time.time()
    for i, r in enumerate(todo, 1):
        url = r["url"]
        slug = slug_of(url)
        text, code = fetch_body(url)
        if text and len(text) >= 200:
            have[slug] = {"url": url, "company": r.get("company", ""),
                          "title": r.get("title", ""), "price": r.get("price", 0),
                          "text": text, "chars": len(text),
                          "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            got += 1
            lens.append(len(text))
        else:
            fail += 1
            have.setdefault(slug, {"url": url, "company": r.get("company", ""),
                                   "title": r.get("title", ""), "price": r.get("price", 0),
                                   "text": "", "chars": 0, "code": code,
                                   "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        if i % 25 == 0 or i == len(todo):
            OUT.write_text(json.dumps(have, ensure_ascii=False), encoding="utf-8")
            el = time.time() - started
            print(f"    {i}/{len(todo)}  ok={got} fail={fail} 中央値={int(sorted(lens)[len(lens)//2]) if lens else 0}字"
                  f"  {el:.0f}s")
        time.sleep(0.55)
    OUT.write_text(json.dumps(have, ensure_ascii=False), encoding="utf-8")

    ok = [v for v in have.values() if v.get("chars", 0) >= 200]
    cl = sorted(v["chars"] for v in ok)
    print(f"  saved: {OUT.name}  entries={len(have)}  本文あり={len(ok)}")
    if cl:
        print(f"  本文長: min={cl[0]} 中央値={cl[len(cl)//2]} p90={cl[int(len(cl)*0.9)]} max={cl[-1]}")
    api_len = 240
    if cl:
        print(f"  API の 240 字に対して {cl[len(cl)//2]/api_len:.1f} 倍の本文")
    print(f"  今回: ok={got} fail={fail} ({(time.time()-started):.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
