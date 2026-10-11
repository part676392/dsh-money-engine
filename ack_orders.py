#!/usr/bin/env python3
"""受領した注文に、paid への道を自動で返す (人間の初動を要らなくする)。

実測 (2026-10-11): 注文 issue は受領して台帳には載る (GH-3 受領 (送金待ち)) が、
買い手に「いくらをどこへ送ればいいのか」を返す口が無く、ここで人が要る状態だった。
受信箱は受信専用で外送信できないので、返事は issue のコメントに出す。
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parent
REPO = "part676392/dsh-money-engine"
JST = timezone(timedelta(hours=9))
CHAINS = ("Base", "Arbitrum", "Polygon", "Ethereum")


def gh(args: list, inp: str | None = None) -> tuple:
    r = subprocess.run(["gh"] + args, input=inp, capture_output=True, text=True, timeout=90)
    return r.returncode, r.stdout, r.stderr


def wallet_address() -> str:
    f = ROOT / "outbox" / "wallet.json"
    if not f.exists():
        return ""
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("address") or ""
    except Exception:  # noqa: BLE001
        return ""


def corpus_note() -> str:
    """本の数ではなく、落ちている実測を返す (manifest を読む)。"""
    import csv
    f = ROOT / "exports" / "manifest.csv"
    if not f.exists():
        return ""
    want = {"interview_questions.csv": "面接質問",
            "company_pages.csv": "企業頁",
            "selection_signals.csv": "選考段階の言及"}
    bits = []
    try:
        for r in csv.DictReader(f.read_text(encoding="utf_8_sig").splitlines()):
            k = r.get("file")
            if k in want:
                bits.append(f"{want[k]} {int(str(r.get('rows') or 0).replace(',', '')):,} 行")
    except Exception:  # noqa: BLE001
        return ""
    return " / ".join(bits)


def plan_and_price(body: str) -> tuple:
    """rendered form の '### プラン' 節からプラン語と $ 額を出す。"""
    m = re.search(r"###\s*プラン\s*\n+(.+?)\n", body or "")
    plan = (m.group(1).strip() if m else "")
    p = re.search(r"\$\s?([0-9,]+)", plan)
    if not p:  # プラン語が抜けた本文でも諦めない (全節から拾う)
        p = re.search(r"\$\s?([0-9,]+)", body or "")
    return plan, (p.group(1).replace(",", "") if p else "")


def reply_body(plan: str, price: str, addr: str) -> str:
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    lines = [
        "自動応答です (巡回が出していて、まだ人間は見ていません)。",
        "",
        f"- プラン: {plan or '(本文から読めませんでした。このコメントで教えて下さい)'}",
        f"- 金額: {('$' + price + ' USD') if price else '(金額を本文から読めませんでした)'}",
        f"- 送金先: `{addr}`",
        f"- チェーン: {' / '.join(CHAINS)} (EVM なので 1 つのアドレスで 4 chain 受取れます)",
        "- gas は送付元でご負担ください。着金はこちらの巡回が残高で確認します (確認もこの issue に出ます)",
        "- 納品: 着金確認後、この issue のコメントに CSV / ZIP の公開URLと行数を載せます",
        "- カード払い (Gumroad) は受取先の登録待ちでまだ開いていません。開いたらこの頁に出ます",
        "- 企業名の変更・追加はこの issue のコメントに 1行1社 で書けば差し替えます",
    ]
    note = corpus_note()
    if note:
        lines.append(f"- 今の収録 ({now}): {note}")
    return "\n".join(lines)


def main() -> int:
    selftest = "--selftest" in sys.argv
    body = ("### プラン\n\nカスタム抽出 〜50社 ($15)\n\n### 必要な企業の一覧 (または語彙・業種)\n\n西日本旅客鉄道株式会社\n")
    if selftest:
        plan, price = plan_and_price(body)
        ok = plan == "カスタム抽出 〜50社 ($15)" and price == "15"
        print(f"    注文の自動返信  : {'OK' if ok else '★'} 自己点検 (プラン {plan!r} / $ {price})")
        return 0 if ok else 1

    dpath = ROOT / "data" / "deliveries.json"
    if not dpath.exists():
        print("    注文の自動返信  : 台帳が無いので省略")
        return 0
    led = json.loads(dpath.read_text(encoding="utf-8"))
    todo = [(k, v) for k, v in led.items()
            if k.startswith("GH-") and "受領" in str(v.get("status", "")) and not v.get("acked_at")]
    if not todo:
        print("    注文の自動返信  : 未返信の注文なし")
        return 0
    addr = wallet_address()
    if not addr:
        print("    注文の自動返信  : ★ outbox/wallet.json が読めない (送金先を出せない)")
        return 1
    replied = 0
    for k, v in todo:
        num = k.split("-")[-1]
        rc, out, err = gh(["api", f"repos/{REPO}/issues/{num}"])
        if rc != 0:
            print(f"    注文の自動返信  : ★ #{num} が読めない {err[:70]}")
            continue
        d = json.loads(out)
        labs = [l.get("name", "") for l in (d.get("labels") or [])]
        if "rehearsal" in labs:
            v["acked_at"] = "rehearsal (練習なので返事を飛ばした)"
            print(f"    注文の自動返信  : #{num} は練習 -> 返信を飛ばした")
            continue
        plan, price = plan_and_price(d.get("body") or "")
        text = reply_body(plan, price, addr)
        rc2, out2, err2 = gh(["api", "-X", "POST", f"repos/{REPO}/issues/{num}/comments",
                             "-f", f"body={text}"])
        if rc2 != 0:
            print(f"    注文の自動返信  : ★ #{num} comment 失敗 {err2[:90]}")
            continue
        url = json.loads(out2).get("html_url", "")
        v["acked_at"] = datetime.now(JST).isoformat(timespec="seconds")
        v["ack_url"] = url
        replied += 1
        print(f"  ★ 自動返信 #{num}: {url}")
    if led:
        dpath.write_text(json.dumps(led, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"    注文の自動返信  : OK ({len(todo)} 件中 {replied} 件に返信)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
