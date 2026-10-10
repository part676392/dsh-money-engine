#!/bin/bash
# 受理ドメインの政策はインスタンス毎に違う。実登録を回して許可される所を探す。
cd "$(dirname "$0")"
for INST in mastodon.art infosec.exchange vis.social hachyderm.io mastodon.uno mastodon.world; do
  echo "--- $INST ---"
  node signup_mastodon.js "$INST" 2>&1 | tail -2 | tr -d '\n' | cut -c1-160; echo
  python3 -c "
import json
try:
    d=json.load(open('outbox/mastodon-signup.json'))
    ok_host = d.get('host') == "$INST".strip()
    print('   reached=%s host=%s (target match=%s) errs=%s' % (d.get('reached'), d.get('host'), ok_host, (d.get('errs') or d.get('problem') or d.get('blocked') or '')[:110]))
    if not ok_host:
        print('   ★ 記録がこのインスタンスのものではない = 実行されていない')
    print('   url=%s' % str(d.get('url'))[:80])
except Exception as e:
    print('   記録なし', e)
"
  R=$(python3 -c "import json;d=json.load(open('outbox/mastodon-signup.json'));print(d.get('reached') and d.get('host')=='$INST')" 2>/dev/null)
  if [ "$R" = "True" ]; then echo "   ★ 登録通った: $INST"; break; fi
  sleep 4
done
