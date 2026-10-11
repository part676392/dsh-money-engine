#!/usr/bin/env python3
"""访问計の JS を1箇所だけの実装に寄せる。

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


def tracker(key: str) -> str:
    """頁に1個入れる <script>。
    - 鍵 `key` を叩く (頁別の計数)
    - `?src=<token>` があれば `src-<token>` も叩く (流入源)
    - `document.referrer` の host を `ref-<host>` で叩き、全量を `ref-any` に足す。
      自サイト内遷移 (same host) は数えない。
    """
    return (
        '<script>(function(){try{var b="'
        + ABACUS
        + '";fetch(b+"'
        + key
        + '", {mode:"no-cors",keepalive:true});'
        + "var m=(location.search.match(/[?&]src=([a-z0-9_-]{1,24})/)||[])[1];"
        + "if(m){fetch(b+'src-'+m, {mode:'no-cors',keepalive:true});}"
        + "var r='';try{r=document.referrer||'';}catch(e2){}"
        + "if(r){try{var h=new URL(r).hostname.toLowerCase().replace(/[^a-z0-9.-]/g,'');"
        + "if(h&&h!==" + SELF_HOST_MARK + "){"
        + "fetch(b+'ref-'+h,{mode:'no-cors',keepalive:true});"
        + "fetch(b+'ref-any',{mode:'no-cors',keepalive:true});}}catch(e3){}}"
        + "}catch(e){}})();</script>"
    )


def beacon_js(key: str) -> str:
    """onclick 用の beacon。abacus の URL はこの file でしか作らない (単一実装の護りを壊さない)。"""
    return "fetch('" + ABACUS + key + "',{mode:'no-cors',keepalive:true})"


if __name__ == "__main__":
    print(tracker("home"))
