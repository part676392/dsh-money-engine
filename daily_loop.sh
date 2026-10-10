#!/bin/bash
# 無人日次ループ: 締切を update → サイト再生成 → push → Pages ビルド → IndexNow → 得点盤
# GitHub Actions の workflow scope 不要。この Mac の launchd から回る。
set -uo pipefail
cd "$(dirname "$0")" || exit 1
LOG="logs/daily_$(date +%Y%m%d).log"
mkdir -p logs
{
  echo "===== $(date '+%F %T') start ====="
  git pull --rebase --quiet origin main 2>&1 | tail -2

  python3 extract_deadlines.py 2>&1 | tail -3
  python3 make_deadlines.py  2>&1 | tail -2
  python3 build_site.py       2>&1 | tail -2

  git add -A
  if ! git diff --cached --quiet; then
    git -c user.name="part676392" -c user.email="72697109+part676392@users.noreply.github.com" \
        commit -qm "daily refresh $(date +%F)"
    TOK=$(gh auth token 2>/dev/null)
    git push -q "https://x-access-token:${TOK}@github.com/part676392/dsh-money-engine.git" HEAD:main \
      && echo "  pushed" || echo "  PUSH FAILED"
    gh api -X POST repos/part676392/dsh-money-engine/pages/builds >/dev/null 2>&1 && echo "  pages build triggered"
    sleep 30
  else
    echo "  nothing changed"
  fi

  KEY=$(cat data/indexnow.key)
  BASE=https://part676392.github.io/dsh-money-engine
  python3 - "$KEY" "$BASE" <<'PY'
import json,sys,urllib.request,urllib.error
key,base=sys.argv[1],sys.argv[2]
import pathlib
urls=[f"{base}/",f"{base}/es-deadlines.html"]
try:
    dem=json.load(open("data/demand_raw.json"))
    per=dem.get("per_company",{})
    top=sorted(((k,v.get("count",0)) for k,v in per.items() if v.get("count",0)>0),key=lambda x:-x[1])[:25]
    for k,_ in top:
        import urllib.parse,os
        f=f"company/{urllib.parse.quote(k)}.html"
        if os.path.exists(f): urls.append(f"{base}/{f}")
except Exception as e:
    print("  demand urls skipped",e)
pl={"host":"part676392.github.io","key":key,"keyLocation":f"{base}/{key}.txt","urlList":urls}
for ep in ["https://api.indexnow.org/indexnow","https://www.bing.com/indexnow"]:
    r=urllib.request.Request(ep,data=json.dumps(pl).encode(),headers={"Content-Type":"application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(r,timeout=40) as x: print(f"  indexnow {ep.split('//')[1]:26s} {x.status} ({len(urls)} urls)")
    except urllib.error.HTTPError as e: print(f"  indexnow {ep.split('//')[1]:26s} {e.code}")
PY

  python3 scoreboard.py 2>&1 | tail -3
  echo "===== $(date '+%F %T') end ====="
} >> "$LOG" 2>&1
