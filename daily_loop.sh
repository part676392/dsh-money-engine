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
  python3 log_run.py start
  # token 必須の理由を測り直した (2026-10-11):
  #   - 空 token でも pull は通る (repo が public なので無名 read が効く。実測で SHA が返った)
  #   - 非tty では git は認証を聞いてハングしない (即失敗した)
  #   - 壊れるのは push だけ。つまり空 token の run は「集めて出版できない」
  # よってこのガードの意味はハング回避ではなく **出版できない run を最初の1行で止めて
  # 日志に痕を残す**こと。GIT_TERMINAL_PROMPT=0 は対話環境で聞かれないための保険。
  # 因みに start だけ書いて何も出さない run の真因は、巡回を `| head` に繋いだ
  # 側の SIGPIPE (検証手法のミス)。日志を見る時は >/dev/null で回すこと。
  export GIT_TERMINAL_PROMPT=0
  TOK0=$(gh auth token 2>/dev/null)
  if [ -z "$TOK0" ]; then
    echo "  ★★★ GUARD FAIL: gh token が空 (git pull で固まる前に終了)"
    echo "===== $(date '+%F %T') abort (no token) =====" >> "$LOG"
    exit 1
  fi
  git pull --rebase --autostash --quiet "https://x-access-token:${TOK0}@github.com/part676392/dsh-money-engine.git" main 2>&1 | tail -2

  python3 ensure_inbox.py     2>&1 | tail -4
  python3 extract_deadlines.py 2>&1 | tail -3
  python3 make_deadlines.py  2>&1 | tail -2

  git add -A
  if ! git diff --cached --quiet; then
    # 劣化してから push しない。runner を ~/Documents の外に移すと
    # full_bodies.json の無い環境が現れ、質問頁が 1,779 → 94 行に縮んで
    # も日志には何も出ない。だから数を見て止める (check_regression.py)。
    # 言葉の護り: 「管線が物を-create できる」のような混入が live に出た実測がある。
    # 目視は通りすがるので、混入が見つかったら push を止める。
    if ! python3 lint_prose.py; then
      echo "  ★★★ GUARD FAIL: prose — 日本語の文中に英語の動詞が混ざった頁がある。push 見送り"
      git reset -q --hard HEAD
    elif ! python3 check_regression.py; then
      echo "  ★★★ GUARD FAIL: regression — published を劣化させる再生成なので push 見送り"
      git reset -q --hard HEAD
    else
    git -c user.name="part676392" -c user.email="72697109+part676392@users.noreply.github.com" \
        commit -qm "daily refresh $(date +%F)"
    TOK=$(gh auth token 2>/dev/null)
    git push -q "https://x-access-token:${TOK}@github.com/part676392/dsh-money-engine.git" HEAD:main \
      && echo "  pushed" || echo "  PUSH FAILED"
    python3 check_regression.py --update 2>&1 | tail -1
    gh api -X POST repos/part676392/dsh-money-engine/pages/builds >/dev/null 2>&1 && echo "  pages build triggered"
    sleep 30
    fi
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
      f"{base}/store/",f"{base}/store/mini.html",f"{base}/ai-interviews.html",f"{base}/selection-signals.html",f"{base}/selection-flows.html"]
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
  python3 retag_links.py       2>&1 | tail -3   # 面が ?src= を保っているか (自分の面だけ)
  python3 publish_rentry.py      2>&1 | tail -5
  python3 check_hn.py            2>&1 | tail -3
  python3 check_traffic.py 2>&1 | tail -12   # 4鍵+pixel+見出し。6 だと store/home が消える (実測になった)
  python3 check_indexation.py    2>&1 | tail -14
  python3 check_payment.py 2>&1 | tail -7
  python3 check_orders.py 2>&1 | tail -14
  python3 check_orders.py --selftest 2>&1 | tail -3
  python3 check_payment_rail.py 2>&1 | tail -5
  python3 money_check.py          2>&1 | tail -6
  python3 secrets_check.py       2>&1 | tail -7
  python3 check_signup_rails.py 2>&1 | tail -6
  python3 scoreboard.py 2>&1 | tail -3
  python3 harvest_full.py 200   2>&1 | tail -3
  python3 make_question_lineups.py 2>&1 | tail -3
  python3 make_reverse_questions.py 2>&1 | tail -3
  python3 make_interview_questions.py 2>&1 | tail -6
  python3 make_selection_flows.py 2>&1 | tail -7
  python3 make_selection_signals.py 2>&1 | tail -3
  python3 make_exports.py        2>&1 | tail -6
  python3 build_dataset_store.py 2>&1 | tail -4
  python3 build_sample.py        2>&1 | tail -6
  python3 build_rehearsals.py    2>&1 | tail -4
  python3 build_deliveries.py    2>&1 | tail -3
  python3 make_release.py        2>&1 | tail -4
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
      && echo "  history push ok (exit)" || echo "  HISTORY PUSH FAILED"
    # exit=0 は証じゃない (自分がそう習った)。local と remote の full SHA を突き合わせる。
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git ls-remote "https://x-access-token:${TOK2}@github.com/part676392/dsh-money-engine.git" HEAD | cut -f1)
    if [ -n "$REMOTE" ] && [ "$LOCAL" = "$REMOTE" ]; then
      echo "  history pushed (SHA 一致 ${LOCAL:0:10})"
    else
      echo "  ★ PUSH UNCONFIRMED local=${LOCAL:0:10} remote=${REMOTE:0:10}"
    fi
    gh api -X POST repos/part676392/dsh-money-engine/pages/builds >/dev/null 2>&1
  fi
  # 守りの集計。各検査は print するだけで exit を汚さないので、赤が出ても
  # 無人実行は朝まで黙ったまま通る (2026-10-11 の secret ignore 漏れが実例)。
  # だから今回の分だけ切り出して赤を1行の警告と状態ファイルにする。
  RUN=$(awk '/start =====/{buf=""} {buf=buf "\n" $0} END{print buf}' "$LOG")
  FAIL=""
  echo "$RUN" | grep -q "no secret in public repo: False" && FAIL="$FAIL secret"
  echo "$RUN" | grep -q "money pages ready: False" && FAIL="$FAIL money"
  echo "$RUN" | grep -q "AEO claim holds: False" && FAIL="$FAIL aeo"
  echo "$RUN" | grep -q "PUSH UNCONFIRMED" && FAIL="$FAIL push"
  echo "$RUN" | grep -q "GUARD FAIL: regression" && FAIL="$FAIL regression"
  echo "$RUN" | grep -q "GUARD FAIL: prose" && FAIL="$FAIL prose"
  echo "$RUN" | grep -qE "parser self-test: ([0-3])/4" && FAIL="$FAIL parser"
  if [ -n "$FAIL" ]; then
    echo "  ★★★ GUARD FAIL:$FAIL  (ログのこの行を目安にすること)"
  else
    echo "  guards: all green"
  fi
  python3 - "$FAIL" <<'GUARD'
import json, pathlib, sys, time
fails = [f for f in sys.argv[1].split() if f]
p = pathlib.Path("data/rails/guards_latest.json")
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps({
    "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "green": not fails, "failed": fails}, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"  guards state written: green={not fails} failed={fails or '[]'}")
GUARD
  python3 log_run.py end guards="${FAIL:-green}"
  echo "===== $(date '+%F %T') end ====="
} >> "$LOG" 2>&1
