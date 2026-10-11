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
  # push の前に remote を取り込む (実行中に dev 側が push するのが実測)。
  # pull --rebase だけだと data/history/index.json が揉めて、rebase 中断のまま
  # 501 file を抱えて次回を迎えた (2026-10-11 09:47 実測)。
  # 取りに行く順: fetch -> merge (-X theirs) -> 揉めたら remote を正に reset。
  # 落とすのは巡回が作った頁だけなので、作り直せば戻る (手作業の資産は無い)。
  sync_push() {
    _O="$1"
    if ! git fetch -q "$_O" main; then
      echo "  sync: fetch 失敗 (ネットワーク?) -> push だけ試す"
    elif ! git merge --no-edit -X theirs FETCH_HEAD >/dev/null 2>&1; then
      echo "  sync: merge が揉めたので remote を正に戻す (作り直せるものだけ)"
      git rebase --abort 2>/dev/null
      git reset -q --hard FETCH_HEAD
    fi
    git push -q "$_O" HEAD:main
  }

# Pages の build を同じ commit で二重に走らせない。legacy Pages は競合すると
# "Page build failed." を出すだけで live は正しかった (2026-10-11 実測:
# 同じ commit に built と errored が並んだ)。護りは HEAD が配られたかだけを見る。
pages_trigger() {
  _U="$1"
  _SHA=$(git ls-remote "$_U" HEAD 2>/dev/null | cut -f1)
  _ST=$(gh api "repos/part676392/dsh-money-engine/pages/builds?per_page=12" --jq '.[] | "\(.status) \(.commit)"' 2>/dev/null)
  if [ -n "$_SHA" ] && printf "%s" "$_ST" | grep -qE "^(built|building|queued) ${_SHA}$"; then
    echo "  pages: HEAD の build が既にある (飛ばす)"
  else
    gh api -X POST repos/part676392/dsh-money-engine/pages/builds >/dev/null 2>&1 \
      && echo "  pages build 指示"
  fi
}

pages_check() {
  _U="$1"
  _SHA=$(git ls-remote "$_U" HEAD 2>/dev/null | cut -f1)
  if [ -z "$_SHA" ]; then echo "  pages build: 照合出来ず (remote SHA が読めない)"; return 0; fi
  _PEND=0
  for _t in $(seq 1 10); do
    _ST=$(gh api "repos/part676392/dsh-money-engine/pages/builds?per_page=15" --jq '.[] | "\(.status) \(.commit)"' 2>/dev/null)
    if printf "%s" "$_ST" | grep -q "^built ${_SHA}$"; then
      echo "  pages build: HEAD が built (live は最新)"
      return 0
    fi
    _PEND=$(printf "%s" "$_ST" | grep -cE "^(building|queued) ${_SHA}$")
    if [ "$_PEND" -gt 0 ] && [ "$_t" -lt 10 ]; then
      echo "  pages build: HEAD を build 中 ($_t/10 を待つ)"
      sleep 30
      continue
    fi
    break
  done
  _LATEST=$(printf "%s" "$_ST" | head -1)
  if [ "$_PEND" -gt 0 ]; then
    echo "  pages build: ★ HEAD の build が 300 秒たっても終わらない / latest=${_LATEST}"
  else
    echo "  pages build: ★ HEAD の built が無い (無いか errored) / latest=${_LATEST}"
  fi
  echo "  ★★★ GUARD FAIL: pages — Pages に HEAD が配られていない (live が古い)"
}
  TOK0=$(gh auth token 2>/dev/null)
  if [ -z "$TOK0" ]; then
    echo "  ★★★ GUARD FAIL: gh token が空 (git pull で固まる前に終了)"
    echo "===== $(date '+%F %T') abort (no token) =====" >> "$LOG"
    exit 1
  fi
  git pull --rebase --autostash --quiet "https://x-access-token:${TOK0}@github.com/part676392/dsh-money-engine.git" main 2>&1 | tail -2

  python3 ensure_inbox.py     2>&1 | tail -4
  python3 extract_deadlines.py 2>&1 | tail -3
# 護りが読むのは disk の頁。再生成の直後に囀す (idempotent)。
# polish を末尾だけにおいていたら money_check が上部欄の無い頁を見て ★ を撒いた (実測)。
  python3 polish_buy_bars.py     2>&1 | tail -1
# 全 600 記事の本文を network から引く広い抽出 (実測 ~8 分 / 0.35 秒 sleep)。
# 1 日 1 回だけ: 3 枠 x 毎巡回でやると note 側に負荷を掛けすぎるので回数を守る。
# 実測: これを手動・dev だけでやっていたので、runner の締切頁は古い wide に基づいていた。
WIDE_MARK="logs/.wide_$(date +%Y%m%d)"
mkdir -p logs
if [ ! -f "$WIDE_MARK" ]; then
  echo "  広い締切抽出を開始 (600 記事)"
  if python3 extract_deadlines_wide.py 2>&1 | tail -3; then
    touch "$WIDE_MARK"
    find logs -name ".wide_*" -mtime +14 -delete 2>/dev/null || true
  else
    echo "  ★ 広い締切抽出が落ちた (今日は mark を置かないので次回やり直す)"
  fi
else
  echo "  広い締切抽出: 今日は済み ($WIDE_MARK)"
fi
  python3 make_deadlines.py  2>&1 | tail -2
  # 商店 (data-license) は締切の個数を書くので、締切頁を作った直後に作り直す。
  # 実測: make_deadlines (96行) で頁が 15 件、build_dataset_store (253行) まで data-license が 12 件
  # のままだったので、個数一致の護りが正直に割れを見て push を見送った (guards=regression)。
  python3 build_dataset_store.py 2>&1 | tail -1

  # secret を public に押してから ★ が出る順番が逆だった (実測: .note-profile/ 487 件を
  # push した後に secrets 護りが ★ を出した)。Playwright の永続 profile は commit しない。
  git add -A -- . ":(exclude)*-profile/" 2>/dev/null || git add -A
  python3 secrets_check.py 2>&1 | tail -3
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
    sync_push "https://x-access-token:${TOK}@github.com/part676392/dsh-money-engine.git" \
      && echo "  pushed" || echo "  PUSH FAILED"
    python3 check_regression.py --update 2>&1 | tail -1
    pages_trigger "https://x-access-token:${TOK}@github.com/part676392/dsh-money-engine.git"
    sleep 40
    pages_check "https://x-access-token:${TOK}@github.com/part676392/dsh-money-engine.git"
    sleep 30
    fi
  else
    echo "  nothing changed"
  fi

  KEY=$(cat data/indexnow.key)
  BASE=https://part676392.github.io/dsh-money-engine
  python3 - "$KEY" "$BASE" <<'PY'
import json,sys,time,urllib.request,urllib.error
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
    import re as _re
    def canon(f):
        """別名の連絡頁 (noindex) は検索に渡さない。本体の URL に引き直す。"""
        h=open("company/"+f,encoding="utf-8",errors="replace").read()
        # refresh の URL は url= (小文字) で書かれている。大文字 only にすると別名を
        # そのまま検索に渡す (実測: 付録頁 company/トヨタ自動車.html)。
        m=_re.search(r'''http-equiv="refresh"[^>]*?url=([^"'>]+)''',h,_re.I)
        if not m:
            m=_re.search(r'<link rel="canonical" href="([^"]+)"',h)
        if not m: return f,None
        tgt=urllib.parse.unquote(m.group(1)).rstrip("/").split("/")[-1]
        return (tgt,f) if tgt and pathlib.Path("company/"+tgt).exists() else (None,f)
    misses=[]; alias=0
    for k,_ in top:
        f=resolve(k)
        if not f:
            misses.append(k); continue
        f,was=canon(f)
        if not f:
            misses.append(k); continue
        if was and was!=f: alias+=1   # 本体は canonical が自分自身なので数えない
        urls.append(f"{base}/company/{urllib.parse.quote(f)}")
    if alias: print(f"  (別名 {alias} 本は本体 URL に引き直して送信)")
    if misses: print(f"  (no page for {len(misses)} demand-top companies: {misses[:6]})")
except Exception as e:
    print("  demand urls skipped",e)
# sitemap の全 URL を送る。前は根 8 本 + demand top 40 だけで、
# sitemap 486 本のうち 48 本しか検索に渡していなかった (2026-10-11 実測)。
sm_urls=[]
try:
    import re as _re
    sm_urls=_re.findall(r"<loc>(.*?)</loc>",pathlib.Path("sitemap.xml").read_text(encoding="utf-8"))
    n0=len(urls)
    for u in sm_urls:
        if u not in urls: urls.append(u)
    print(f"  sitemap から {len(urls)-n0} 本を追加 (送信 {len(urls)} / sitemap {len(sm_urls)})")
except Exception as e:
    print("  sitemap merge skipped",e)
urls=urls[:5000]
pl={"host":"part676392.github.io","key":key,"keyLocation":f"{base}/{key}.txt","urlList":urls}
for ep in ["https://api.indexnow.org/indexnow","https://www.bing.com/indexnow"]:
    r=urllib.request.Request(ep,data=json.dumps(pl).encode(),headers={"Content-Type":"application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(r,timeout=40) as x: print(f"  indexnow {ep.split('//')[1]:26s} {x.status} ({len(urls)} urls)")
        pathlib.Path("data/rails").mkdir(parents=True,exist_ok=True)
        json.dump({"at":time.strftime("%Y-%m-%dT%H:%M:%S%z"),"endpoint":ep,"submitted":len(urls),
                   "sitemap":len(sm_urls),"status":x.status,"urls":urls[:5200]},
                  open("data/rails/indexnow_latest.json","w"),ensure_ascii=False,indent=1)
    except urllib.error.HTTPError as e:
        print(f"  indexnow {ep.split('//')[1]:26s} {e.code}")
        pathlib.Path("data/rails").mkdir(parents=True,exist_ok=True)
        json.dump({"at":time.strftime("%Y-%m-%dT%H:%M:%S%z"),"endpoint":ep,"submitted":len(urls),
                   "sitemap":len(sm_urls),"status":e.code,"urls":urls[:5200]},
                  open("data/rails/indexnow_latest.json","w"),ensure_ascii=False,indent=1)
PY

  python3 check_distribution.py 2>&1 | tail -7
  if ! python3 retag_links.py 2>&1 | tail -4; then
    # 面に貼った link が死んでいたり ?src= を失っていると、人が来ても計数に残らない
    echo "  ★★★ GUARD FAIL: surface-links — 面の link が死んでいるか ?src= を失った"
  fi
  python3 publish_rentry.py      2>&1 | tail -5
  python3 check_hn.py            2>&1 | tail -3
  if ! python3 check_traffic.py 2>&1 | tail -12; then
    # 計数が読めない日は「0 件」ではなく未取得。測れない日を日志に残す。
    echo "  ★★★ GUARD FAIL: traffic — 流入の計数が読めない (未取得)"
  fi   # 4鍵+pixel+見出し。6 だと store/home が消える (実測になった)
  if ! python3 check_indexation.py 2>&1 | tail -14; then
    # 発見の配管 (sitemap 全量の IndexNow 送信 / key file / robots) が切れたら日志に ★
    echo "  ★★★ GUARD FAIL: discovery — 索引に渡す配管が切れている"
  fi
  if ! python3 check_index_probe.py 2>&1 | tail -3; then
    # 索入室が測れない日 (クエリ壊れ / 結果頁の外殻無し) を 0 件と混ぜない
    echo "  ★★★ GUARD FAIL: index-probe — 索入室を測れなかった (0 件と区別する)"
  fi
  if ! python3 check_source_liveness.py 2>&1 | tail -4; then
    # 出典が死んだ / 有料化 / 測れない を面の約束の違反として立てる
    echo "  ★★★ GUARD FAIL: source-liveness — 出典URLの生存が変わったか測れていない"
  fi
  # 唯一 人が辿れている入口 (PR 本文の link) の点検。計数が落ちるまで分からなかった (実測)。
  # 全站のメール口を今の文面で作り直す (builder が inject を呼ばない 11 頁が腐っていた)。
  if ! python3 refresh_order_blocks.py 2>&1 | tail -3; then
    RUN="$RUN
$(date ...) 古いメール文面 ★"
    echo "  ★★★ GUARD FAIL: mail-copy — 古い料金語のメール口が残っている"
  fi
  if ! python3 check_pr_links.py 2>&1 | tail -4; then
    RUN="$RUN
$(date ...) PR 入口 ★"
    echo "  ★★★ GUARD FAIL: pr-links — 人が辿れている入口の link が消えたか読めない"
  fi
  python3 check_payment.py 2>&1 | tail -7
  python3 check_orders.py 2>&1 | tail -14
  python3 check_orders.py --selftest 2>&1 | tail -3
  python3 check_payment_rail.py 2>&1 | tail -5
# 護りが読むのは disk の頁。再生成の直後に囀す (idempotent)。
# polish を末尾だけにおいていたら money_check が上部欄の無い頁を見て ★ を撒いた (実測)。
  python3 polish_buy_bars.py     2>&1 | tail -1
  python3 money_check.py          2>&1 | tail -6
  if ! python3 check_card_surface.py 2>&1 | tail -5; then
    # 料金を出す面にカード口が無く、しかも『買えない』と書いて無い = 嘘の店
    echo "  ★★★ GUARD FAIL: card-surface — 料金を出す面がカードで買えず、正直な注記も無い"
  fi
  python3 secrets_check.py       2>&1 | tail -7
  python3 check_signup_rails.py 2>&1 | tail -6
  python3 scoreboard.py 2>&1 | tail -3
  python3 harvest_full.py 200   2>&1 | tail -3
  python3 make_question_lineups.py 2>&1 | tail -3
  python3 make_reverse_questions.py 2>&1 | tail -3
  python3 make_interview_questions.py 2>&1 | tail -6
  python3 make_selection_flows.py 2>&1 | tail -7
  python3 make_selection_signals.py 2>&1 | tail -3
  # 履歴の行列表は页より先に作る (manifest と $25 の preview が読む)。build_site の後でもう一度。
  python3 make_history_series.py 2>&1 | tail -3
  python3 make_exports.py        2>&1 | tail -6
  python3 build_dataset_store.py 2>&1 | tail -4
  # Gist 2 本は data から作り直す (作っただけだと締切が凍る)。CSV が出来上がった後に置く。
  python3 make_gists.py           2>&1 | tail -2
  python3 build_sample.py        2>&1 | tail -6
  # 執筆物の店と mini は巡回に入っておらず、無人では再生成されなかった (2026-10-11 実測:
  # build_store / build_mini が daily_loop に一行も無い)。価格・受信箱・tracker が枯れる。
  python3 build_store.py         2>&1 | tail -4
  python3 build_mini.py          2>&1 | tail -4
  python3 build_rehearsals.py    2>&1 | tail -4
  python3 build_deliveries.py    2>&1 | tail -3
  python3 make_release.py        2>&1 | tail -4
  python3 make_ai_gap.py        2>&1 | tail -2
  python3 make_changes.py       2>&1 | tail -2
  # プロフィール頁 (part676392/part676392) の 数字は data から再生成。手書きだと古くなる (491社 実測)。
  python3 build_profile_readme.py 2>&1 | tail -2
  python3 make_llms.py        2>&1 | tail -2
  # 注文 form (order.yml) の値段と社数は data から作る。手書きだと頁が先に進んで form が古くなる。
  python3 build_issue_template.py 2>&1 | tail -2
  python3 build_site.py       2>&1 | tail -2
  # 企業頁の道しるべ (company_pages.csv) と llms.txt の枚数は build_site が書いた頁を読む。
  # 先に走ると前の回の枚数で出る (実測でズレた) ので、頁を書いた後に作り直す。
  python3 make_exports.py        2>&1 | tail -2
  python3 make_llms.py           2>&1 | tail -1
  python3 make_history_series.py 2>&1 | tail -3
    # 再生成すると h1 直下の注文欄が消えるので、builder の後に必ず囀す
    # (実測: index.html の注文欄は 99% 目に在り、20 アクセスで注文発火 0)。
    python3 polish_buy_bars.py     2>&1 | tail -2
  python3 audit_aeo.py        2>&1 | tail -10
  # 護りが読んだ頁を、この後の builder が書き直していた (実測 3 度目: run 19:35 で
  # check_card_surface が ★ -> 護り (272行) の後に make_question_lineups (280) / build_sample
  # (291) / build_store (294) / build_site (306) が走っていた)。頁を書き終えた後の護りだけを
  # 朝に見る物にする。上の早期護りは signal として残すが集計しない。
  echo "=== final guards $(date +%H:%M:%S) ==="
  python3 polish_buy_bars.py      2>&1 | tail -1
  python3 refresh_order_blocks.py 2>&1 | tail -1
  if ! python3 check_card_surface.py 2>&1 | tail -5; then
    echo "  ★★★ GUARD FAIL: card-surface — 配られる頁で支払いの口 / プラン語 / \$25 / 出典の性質が壊れている"
  fi
  python3 money_check.py          2>&1 | tail -5
  python3 check_regression.py     2>&1 | tail -2
  python3 lint_prose.py           2>&1 | tail -2
  # 履歴頁と計測値はここで再生成したので、二度目の commit で載せる
  # secret を public に押してから ★ が出る順番が逆だった (実測: .note-profile/ 487 件を
  # push した後に secrets 護りが ★ を出した)。Playwright の永続 profile は commit しない。
  git add -A -- . ":(exclude)*-profile/" 2>/dev/null || git add -A
  python3 secrets_check.py 2>&1 | tail -3
  if ! git diff --cached --quiet; then
    git -c user.name="part676392" -c user.email="72697109+part676392@users.noreply.github.com" \
        commit -qm "history refresh $(date +%F)"
    TOK2=$(gh auth token 2>/dev/null)
    # 実行中にこちら側が push されることが実測である (run 中に HISTORY PUSH FAILED になった)。
    # sync_push が remote を取り込んでから push する (rebase 中断で止まらない)。
    sync_push "https://x-access-token:${TOK2}@github.com/part676392/dsh-money-engine.git" \
      && echo "  history push ok (exit)" || echo "  HISTORY PUSH FAILED"
    # exit=0 は証じゃない (自分がそう習った)。local と remote の full SHA を突き合わせる。
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git ls-remote "https://x-access-token:${TOK2}@github.com/part676392/dsh-money-engine.git" HEAD | cut -f1)
    if [ -n "$REMOTE" ] && [ "$LOCAL" = "$REMOTE" ]; then
      echo "  history pushed (SHA 一致 ${LOCAL:0:10})"
    else
      echo "  ★ PUSH UNCONFIRMED local=${LOCAL:0:10} remote=${REMOTE:0:10}"
    fi
    pages_trigger "https://x-access-token:${TOK2}@github.com/part676392/dsh-money-engine.git"
  fi
  # 守りの集計。各検査は print するだけで exit を汚さないので、赤が出ても
  # 無人実行は朝まで黙ったまま通る (2026-10-11 の secret ignore 漏れが実例)。
  # だから今回の分だけ切り出して赤を1行の警告と状態ファイルにする。
    # build を指示したかに関わらず、今配られている build の状態を最後に1回読む。
    # (指示口が2つで片方は条件付き。errored 2 件が出ても日志に何も出なかった実測がある)
    pages_check "https://x-access-token:${TOK2}@github.com/part676392/dsh-money-engine.git"

  RUN=$(awk '/start =====/{buf=""} {buf=buf "\n" $0} END{print buf}' "$LOG")
  # 集計は sentinel の後だけ見る (護りの後に builder が走る順序を直したので、早期の ★ は
  # 参考 signal。sentinel が無い古い logs は今まで通り全部見る)。
  FINAL=$(printf '%s' "$RUN" | awk '/=== final guards/{f=1} f')
  [ -n "$FINAL" ] && RUN="$FINAL"
  FAIL=""
  echo "$RUN" | grep -q "no secret in public repo: False" && FAIL="$FAIL secret"
  echo "$RUN" | grep -q "money pages ready: False" && FAIL="$FAIL money"
  echo "$RUN" | grep -q "AEO claim holds: False" && FAIL="$FAIL aeo"
  echo "$RUN" | grep -q "PUSH UNCONFIRMED" && FAIL="$FAIL push"
  echo "$RUN" | grep -q "GUARD FAIL: regression" && FAIL="$FAIL regression"
  echo "$RUN" | grep -q "GUARD FAIL: prose" && FAIL="$FAIL prose"
  echo "$RUN" | grep -q "GUARD FAIL: traffic" && FAIL="$FAIL traffic"
  echo "$RUN" | grep -q "GUARD FAIL: surface-links" && FAIL="$FAIL surface-links"
  echo "$RUN" | grep -q "GUARD FAIL: pages" && FAIL="$FAIL pages"
  echo "$RUN" | grep -q "GUARD FAIL: discovery" && FAIL="$FAIL discovery"
  echo "$RUN" | grep -q "GUARD FAIL: card-surface" && FAIL="$FAIL card-surface"
  echo "$RUN" | grep -q "GUARD FAIL: index-probe" && FAIL="$FAIL index-probe"
  echo "$RUN" | grep -q "GUARD FAIL: source-liveness" && FAIL="$FAIL source-liveness"
  echo "$RUN" | grep -q "GUARD FAIL: pr-links" && FAIL="$FAIL pr-links"
  echo "$RUN" | grep -q "GUARD FAIL: mail-copy" && FAIL="$FAIL mail-copy"
  echo "$RUN" | grep -q "GUARD FAIL: money-check" && FAIL="$FAIL money-check"
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
