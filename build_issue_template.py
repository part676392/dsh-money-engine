#!/usr/bin/env python3
"""注文 issue の form を data から作る。手書きだと数字が古くなる。実測で見つけた。

実測 (2026-10-11): プランの選択肢が「カスタム抽出 〜491社 ($60)」のまま、
同じ日に会社を束ねて 473 社になった。form だけ前の数を売っていた。
form は金の入口なので、TIER と snapshot から毎回作り直す。

prefill の鍵は GitHub の仕样で field の `id` (plan / companies / chain / contact)。
id を変えると既に配った link が黙って空欄になるので、id は動かせない。
"""
from __future__ import annotations

import json
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / ".github" / "ISSUE_TEMPLATE" / "order.yml"
SNAP = ROOT / "data" / "snapshot-latest.json"

# build_dataset_store の TIER が金の truth。ここでもう一度数えない。
from build_dataset_store import HISTORY_USD, TIER  # noqa: E402

CHAINS = ["Base", "Arbitrum", "Polygon", "Ethereum"]
IDS = ["plan", "companies", "chain", "contact"]   # link との突合対象 (動かさない)


def tier_label(n: int) -> str:
    if n == 1:
        return "1社だけ試す"
    if n >= 100000:
        return "カスタム抽出 全社ぶん"
    return f"カスタム抽出 〜{n}社"


def options(n_companies: int):
    out = []
    for n, usd in TIER:
        lab = tier_label(n)
        if n >= 100000 and n_companies:
            lab = f"カスタム抽出 全社ぶん {n_companies}社"
        out.append(f"{lab} (${usd})")
    out.append(f"歴史スナップショット一式 (${HISTORY_USD})")
    return out


def render(n_companies: int, n_q: int, n_dist: int) -> str:
    opts = "\n".join(f"          - {o}" for o in options(n_companies))
    return f"""name: データ購入の注文 (Order)
description: 抽出プランを指定して注文する。送金は別送 (Base / Arbitrum / Polygon / ETH)。
labels:
  - 注文
body:
  - type: markdown
    attributes:
      value: |
        本文は公開されます。個人情報 (氏名・メール) は書かなくていいです。
        納品はこの issue のコメントに公開URLとして載せます。
        今の収録: 記事 600 本 / 企業 {n_companies} 社 / 面接質問 {n_q:,} 行 (重複を除いた実文 {n_dist:,} 文)。
  - type: dropdown
    id: plan
    attributes:
      label: プラン
      options:
{opts}
  - type: textarea
    id: companies
    attributes:
      label: 必要な企業の一覧 (または語彙・業種)
      description: 1行1社。業種や語彙の指定でも可。
      placeholder: 東日本旅客鉄道株式会社（JR東日本）
    validations:
      required: true
  - type: dropdown
    id: chain
    attributes:
      label: 送金のチェーン
      options:
{chr(10).join(f"        - {c}" for c in CHAINS)}
  - type: input
    id: contact
    attributes:
      label: 連絡先 (任意 / 空欄ならこの issue で連絡)
  - type: markdown
    attributes:
      value: |
        受信箱は受信専用 (外送信不可) なので、納品は公開URLで渡します。
        この form を開いた際に企業名が既に埋まっていた場合は、そのまま送金先を選ぶだけで注文になります。
"""


def main() -> int:
    snap = {}
    if SNAP.exists():
        snap = json.loads(SNAP.read_text(encoding="utf-8"))
    q = {}
    qf = ROOT / "data" / "interview_questions.json"
    if qf.exists():
        q = json.loads(qf.read_text(encoding="utf-8"))
    n_comp = int(snap.get("companies") or 0)
    n_q = int(q.get("questions_total") or 0)
    n_dist = int(q.get("questions_distinct_text") or 0)
    if not n_comp or not n_q:
        print("  ★ snapshot / questions が読めないので form を書き換えない")
        return 1
    body = render(n_comp, n_q, n_dist)
    old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    OUT.write_text(body, encoding="utf-8")
    print(f"  wrote order.yml  options={len(options(n_comp))}  全社ぶん={n_comp}社 "
          f"(${TIER[-1][1]})  bytes={len(body):,}" + ("  (変化なし)" if old == body else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
