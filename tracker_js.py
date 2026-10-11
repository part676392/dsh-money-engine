#!/usr/bin/env python3
"""訪問計の JS を1箇所だけの実装に寄せる。

理由: 同じ script を 7 file が手書き複製していた (実測 2026-10-11:
build_site / build_store / build_mini / build_sample / build_dataset_store /
make_question_lineups / make_reverse_questions)。参照元Measuredを追加したとき
変更は build_site の頁にだけ入り、他は旧 JS のまま live に出ていた。
複製は「 standar 化したつもり」の嘘を作るので、ここを単一の実装にする。
"""
from __future__ import annotations

ABACUS = "https://abacus.jasoncameron.dev/hit/dsh-money-engine/"

# f-string の中で JS の {} を書くと置換フィールドに化けるので、ここで組み立てる。
SELF_HOST_MARK = "location.hostname"

# クローラを UA で分ける。索引の受け取り側 (referrer) が 0 件のあいだ、
# 「検索エンジンのクローラが頁に到達したか」が索引の唯一先に測れる証になる (鍵不要)。
# 順序が意味を持つ: 上から最初に当たった 1 個だけ数える (二重計数を防ぐ)。
BOTS = [
    ("Googlebot|Google-InspectionTool|GoogleOther|APIs-Google|AdsBot-Google", "bot-google"),
    ("bingbot|adidxbot", "bot-bing"),
    ("DuckDuckBot|DuckDuckGo-Garage", "bot-ddg"),
    ("Slurp", "bot-slurp"),
    ("Marginalia", "bot-marginalia"),
    ("MojeekBot", "bot-mojeek"),
    ("bravebot|Brave%20Search", "bot-brave"),
    ("PerplexityBot", "bot-perplexity"),
    ("OAI-SearchBot|ChatGPT-User|GPTBot", "bot-openai"),
    ("ClaudeBot|claude-ai|Claude-Web", "bot-claude"),
    ("CCBot", "bot-ccbot"),
    ("Amazonbot", "bot-amazon"),
    ("Applebot", "bot-apple"),
    ("PetalBot", "bot-petal"),
]
BOT_KEYS = [k for _, k in BOTS] + ["bot-any"]


def tracker(key: str) -> str:
    """頁に1個入れる <script>。
    - 鍵 `key` を叩く (頁別の計数)
    - `?src=<token>` があれば `src-<token>` も叩く (流入源)
    - `?src=selftest` (自分の護り・点検で開いた訪問) は頁計数を汚さず `self-<key>` へ。
      実測 2026-10-11: home 32 / lineup 7 という读数に自分の計測が何件混じるか読めず、
      「部外者が来たか」に答えられなかった。分離すると残りが部外者だけになる。
    - `document.referrer` の host を `ref-<host>` で叩き、全量を `ref-any` に足す。
      自サイト内遷移 (same host) は数えない。
    """
    return (
        '<script>(function(){try{var b="'
        + ABACUS
        + '";'
        + "var m=(location.search.match(/[?&]src=([a-z0-9_-]{1,24})/)||[])[1];"
        + "var ua='';try{ua=(navigator&&navigator.userAgent)||'';}catch(e4){}"
        # 自苑の合図は 2 通り受け付ける: ?src=selftest か、UA に dsh-selftest を巻いた訪問。
        + "var sl=(m==='selftest')||(/dsh-selftest/.test(ua));"
        + "fetch(b+(sl?'self-" + key + "':'" + key + "'), {mode:'no-cors',keepalive:true});"
        + "if(m){fetch(b+'src-'+m, {mode:'no-cors',keepalive:true});}"
        + "var r='';try{r=document.referrer||'';}catch(e2){}"
        + "if(r&&!sl){try{var h=new URL(r).hostname.toLowerCase().replace(/[^a-z0-9.-]/g,'');"
        + "if(h&&h!==" + SELF_HOST_MARK + "){"
        + "fetch(b+'ref-'+h,{mode:'no-cors',keepalive:true});"
        + "fetch(b+'ref-any',{mode:'no-cors',keepalive:true});}}catch(e3){}}"
        # クローラ計数: navigator を読めない環境 (node の護りなど) では黙る
        + "var BS=(sl?[]:" + _bots_js() + ");"
        + "if(ua){for(var i=0;i<BS.length;i++){if(BS[i][0].test(ua)){"
        + "fetch(b+BS[i][1],{mode:'no-cors',keepalive:true});"
        + "fetch(b+'bot-any',{mode:'no-cors',keepalive:true});break;}}}"
        + "}catch(e){}})();</script>"
    )


def _bots_js() -> str:
    """JS 側の [regex, key] 表。Python の BOTS が単一の実装。"""
    inner = ",".join("[/" + pat + "/i,'" + key + "']" for pat, key in BOTS)
    return "[" + inner + "]"


def beacon_js(key: str) -> str:
    """onclick 用の beacon。abacus の URL はこの file でしか作らない (単一実装の護りを壊さない)。"""
    return "fetch('" + ABACUS + key + "',{mode:'no-cors',keepalive:true})"


if __name__ == "__main__":
    print(tracker("home"))
