#!/bin/bash
# 1件ずつ、全ラウンド出力を残す。前に tail -2 で進捗を隠して詰まるのはごめんだ。
cd "$(dirname "$0")"
INST="$1"
LOG="outbox/sweep-${INST}.log"
: > "$LOG"
node signup_mastodon.js "$INST" >> "$LOG" 2>&1
python3 - "$INST" <<'PY'
import json,sys,pathlib
inst=sys.argv[1]
p=pathlib.Path("outbox/mastodon-signup.json")
log=pathlib.Path(f"outbox/sweep-{inst}.log").read_text(errors="replace")
if not p.exists():
    print(f"  {inst}: 記録なし / log末尾: {log[-200:]}"); raise SystemExit
d=json.loads(p.read_text())
match = d.get("host")==inst
print(f"  {inst}: reached={d.get('reached')} target_match={match} rounds={log.count('\"round\"')}")
for k in ("errs","problem","blocked","body_start"):
    if d.get(k): print(f"     {k}: {str(d[k])[:150]}")
PY
