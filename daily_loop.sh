#!/bin/bash
# 無人日次ループ: 締切を update → サイト再生成 → push → Pages ビルド → IndexNow → 得点盤
# GitHub Actions の workflow scope 不要。この Mac の launchd から回る。
set -uo pipefail
cd "$(dirname "$0")" || exit 1
# launchd に渡される PATH には gh が無い (~/.lmstudio/bin にいる)。
# plist 側だけでなくスクリプト自身でも確定させないと、無人実行は
# push だけ静かに失敗して何も出版されない。2026-10-11 に実証済みの故障。
export PATH="$HOME/.lmstudio/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
LOG="logs/daily_$(date +%Y%m%d).log"
mkdir -p logs
{
  echo "===== $(date '+%F %T') start ====="
  TOK0=$(gh auth token 2>/dev/null)
  git pull --rebase --autostash --quiet "https://x-access-token:${TOK0}@github.com/part676392/dsh-money-engine.git" main 2>&1 | tail -2

  python3 ensure_inbox.py     2>&1 | tail -4
  python3 extract_deadlines.py 2>&1 | tail -3
  python3 make_deadlines.py  2>&1 | tail -2

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
urls=[f"{base}/",f"{base}/es-deadlines.html",f"{base}/changes.html",
      f"{base}/store/",f"{base}/store/mini.html",f"{base}/ai-interviews.html"]
try:
    dem=json.load(open("data/demand_raw.json"))
    per=dem.get("per_company",{})
    top=sorted(((k,v.get("count",0)) for k,v in per.items() if v.get("count",0)>0),key=lambda x:-x[1])[:40]
    import urllib.parse,os
    files=[f for f in os.listdir("company") if f.endswith(".html")]
    stems={f[:-5]: f for f in files}
    def resolve(k):
        # サイトと同じ緩い照合。AGC -> AGC（エージーシー）.html を引く。
        if k in stems: return stems[k]
        kl=k.lower()
        for stem,f in stems.items():
            sl=stem.lower()
            if kl in sl or sl in kl: return f
        return None
    misses=[]
    for k,_ in top:
        f=resolve(k)
        if f: urls.append(f"{base}/company/{urllib.parse.quote(f)}")
        else: misses.append(k)
    if misses: print(f"  (no page for {len(misses)} demand-top companies: {misses[:6]})")
except Exception as e:
    print("  demand urls skipped",e)
pl={"host":"part676392.github.io","key":key,"keyLocation":f"{base}/{key}.txt","urlList":urls}
for ep in ["https://api.indexnow.org/indexnow","https://www.bing.com/indexnow"]:
    r=urllib.request.Request(ep,data=json.dumps(pl).encode(),headers={"Content-Type":"application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(r,timeout=40) as x: print(f"  indexnow {ep.split('//')[1]:26s} {x.status} ({len(urls)} urls)")
    except urllib.error.HTTPError as e: print(f"  indexnow {ep.split('//')[1]:26s} {e.code}")
PY

  python3 check_distribution.py 2>&1 | tail -7
  python3 check_traffic.py 2>&1 | tail -6
  python3 check_payment.py 2>&1 | tail -7
  python3 check_orders.py 2>&1 | tail -6
  python3 check_payment_rail.py 2>&1 | tail -5
  python3 check_signup_rails.py 2>&1 | tail -6
  python3 scoreboard.py 2>&1 | tail -3
  python3 make_ai_gap.py        2>&1 | tail -2
  python3 make_changes.py       2>&1 | tail -2
  python3 make_llms.py        2>&1 | tail -2
  python3 build_site.py       2>&1 | tail -2
  python3 audit_aeo.py        2>&1 | tail -10
  # 履歴頁と計測値はここで再生成したので、二度目の commit で載せる
  git add -A
  if ! git diff --cached --quiet; then
    git -c user.name="part676392" -c user.email="72697109+part676392@users.noreply.github.com" \
        commit -qm "history refresh $(date +%F)"
    TOK2=$(gh auth token 2>/dev/null)
    git push -q "https://x-access-token:${TOK2}@github.com/part676392/dsh-money-engine.git" HEAD:main \
      && echo "  history pushed" || echo "  HISTORY PUSH FAILED"
    gh api -X POST repos/part676392/dsh-money-engine/pages/builds >/dev/null 2>&1
  fi
  echo "===== $(date '+%F %T') end ====="
} >> "$LOG" 2>&1
