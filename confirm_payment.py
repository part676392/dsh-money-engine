#!/usr/bin/env python3
"""暗号の着金を拾って、注文 issue に納品物を出す (人が要るようにする)。

実測 (2026-10-11): 残高は data/rails/<日時>.json に total_eth で毎巡回積まっている (0.0 のまま)。
raven (注文) があっても「着いた -> 何を返すか」の口が未実装だったので、ここを通す。
内訳 (どのチェーンからいくら) は RPC から取れないので、合計の増分だけで見る。
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
RAILS = ROOT / "data" / "rails"
JST = timezone(timedelta(hours=9))


def snapshots() -> list:
    out = []
    for p in sorted(RAILS.glob("20*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        c = d.get("crypto") or {}
        if "total_eth" in c:
            out.append((p.name, float(c.get("total_eth") or 0.0), c.get("rpc_ok") or ""))
    return out


def gh(args: list) -> tuple:
    r = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=90)
    return r.returncode, r.stdout, r.stderr


def latest_release() -> dict:
    rc, out, _ = gh(["api", f"repos/{REPO}/releases/latest"])
    if rc != 0:
        return {}
    d = json.loads(out)
    a = (d.get("assets") or [{}])[0]
    return {"tag": d.get("tag_name", ""), "name": a.get("name", ""),
            "url": a.get("browser_download_url", ""), "bytes": a.get("size", 0)}


def awaiting(led: dict) -> list:
    return [(k, v) for k, v in led.items()
            if k.startswith("GH-") and "受領" in str(v.get("status", "")) and not v.get("delivered_at")]


def delivery_text(delta: float, rel: dict, plan: str) -> str:
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    lines = [
        f"着金確認: 受取アドレスの合計残高が +{delta:.6f} ETH 分 増えました ({now})。",
        "",
        f"- プラン: {plan or '(未読)'}",
    ]
    if rel.get("url"):
        lines += [f"- 全データの_zip (歴史スナップショット / {rel['bytes']:,} B): {rel['url']}",
                  f"- tag: `{rel['tag']}` (中身の行数は manifest.csv に有ります)"]
    lines += [
        "- 個別抽出 (カスタム抽出 プラン) は次の巡回で掛けて、別のコメントに URL を載せます",
        "- 金額がプランと合わない場合はこのコメントに書いてください (不足は追撃、過剰は返金します)",
        "- 着金の内訳 (どのチェーンからいくら) は RPC 側で取れないため、合計で見ています",
    ]
    return "\n".join(lines)


def main() -> int:
    if "--selftest" in sys.argv:
        snaps = [("2026-10-11-2201.json", 0.0, "3/4"), ("2026-10-11-2215.json", 0.0125, "4/4")]
        delta = round(snaps[-1][1] - snaps[-2][1], 9)
        txt = delivery_text(delta, {"tag": "snap-x", "name": "snap-x.zip",
                                   "url": "https://x/snap-x.zip", "bytes": 1234}, "歴史スナップショット一式 ($25)")
        ok = delta == 0.0125 and "snap-x.zip" in txt and "+0.012500" in txt
        print(f"    着金の納品      : {'OK' if ok else '★'} 自己点検 (増分 {delta} / 納品文 {len(txt)}字)")
        return 0 if ok else 1

    snaps = snapshots()
    if len(snaps) < 2:
        print("    着金の納品      : 差分が取れない (観測 1 件)")
        return 0
    prev, cur = snaps[-2][1], snaps[-1][1]
    delta = round(cur - prev, 9)
    dpath = ROOT / "data" / "deliveries.json"
    led = json.loads(dpath.read_text(encoding="utf-8")) if dpath.exists() else {}
    pend = awaiting(led)
    if delta <= 0:
        print(f"    着金の納品      : 増分なし ({prev:.6f} -> {cur:.6f}) / 受領中 {len(pend)} 件")
        return 0
    if not pend:
        print(f"  ★ 着金 +{delta:.6f} ETH 増 but 受領中の注文が無い (谁かのお裾分けか、台帳が未反映)")
        return 0
    rel = latest_release()
    posted = 0
    for k, v in pend:
        num = k.split("-")[-1]
        rc, out, _ = gh(["api", f"repos/{REPO}/issues/{num}"])
        plan = ""
        if rc == 0:
            body = json.loads(out).get("body") or ""
            m = re.search(r"###\s*プラン\s*\n+(.+?)\n", body)
            plan = m.group(1).strip() if m else ""
        text = delivery_text(delta, rel, plan)
        rc2, out2, err2 = gh(["api", "-X", "POST", f"repos/{REPO}/issues/{num}/comments",
                             "-f", f"body={text}"])
        if rc2 != 0:
            print(f"    着金の納品      : ★ #{num} comment 失敗 {err2[:80]}")
            continue
        v["delivered_at"] = datetime.now(JST).isoformat(timespec="seconds")
        v["delivery_delta_eth"] = delta
        v["delivery_url"] = json.loads(out2).get("html_url", "")
        v["status"] = "着金確認 (納品 URL 掲載)"
        posted += 1
        print(f"  ★ 着金 -> 納品 #{num}: {v['delivery_url']}")
    if led:
        dpath.write_text(json.dumps(led, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"    着金の納品      : OK (増分 +{delta:.6f} / {len(pend)} 件中 {posted} 件に出した)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
