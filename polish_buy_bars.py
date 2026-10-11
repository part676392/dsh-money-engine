"""面の先頭に注文欄を差し込む (最後の最後だけに有った為)。

実測: 注文欄の有る頁 7 枚すべてで、導線は本文の 77〜99% 目に在った。
      index.html は 145,446 字のうち 99% 目。上部には迂回 link だけ。
 builders は-pages を再生成する度に下書きし直すので、再生成の後に1回囀す所を別に持つ。
 money_check.cta_check が位置も点検する (上 25% 以内に注文の導線)。
"""
from __future__ import annotations

import pathlib
import urllib.parse

import buy_block

ROOT = pathlib.Path(__file__).resolve().parent
TOP_LIMIT = 0.25          # 上部欄と認める位置 (文書の先からの割合)


def company_of(rel: str) -> str:
    """company/<社名>.html から社名を戻す (alias 頁は main で弾く)。"""
    if not rel.startswith("company/"):
        return ""
    stem = pathlib.Path(rel).stem
    return urllib.parse.unquote(stem)


def polish(quiet: bool = False) -> tuple:
    """面の html を歩いて、h1 の直後に上部欄の無い頁を直す。"""
    touched, already, skipped = [], [], []
    files = list(ROOT.glob("*.html")) + list((ROOT / "store").glob("*.html")) \
        + list((ROOT / "company").glob("*.html"))
    for f in files:
        rel = f.name if f.parent == ROOT else f.relative_to(ROOT).as_posix()
        h = f.read_text(encoding="utf-8", errors="replace")
        if 'http-equiv="refresh"' in h:          # 別名の連絡頁は本体へ誘導すれば十分
            skipped.append(rel)
            continue
        if "</h1>" not in h:
            skipped.append(rel)
            continue
        head = h.split("</h1>", 1)[0]
        if "template=order.yml" in head:
            already.append(rel)
            continue
        comp = company_of(rel)
        new = h.replace("</h1>", "</h1>" + buy_block.bar(comp), 1)
        f.write_text(new, encoding="utf-8")
        touched.append(rel)
    if not quiet:
        print(f"  上部の注文欄      : 差し込み {len(touched)} 頁 / 元から有った {len(already)} 頁"
              f" / 対象外 {len(skipped)} 頁")
        if touched[:3]:
            print(f"    例: {touched[:3]}")
    return touched, already, skipped


def positions() -> list:
    """各頁の注文欄が文書の何割目に有るか (護り用)。"""
    out = []
    files = list(ROOT.glob("*.html")) + list((ROOT / "store").glob("*.html")) \
        + list((ROOT / "company").glob("*.html"))
    for f in files:
        if f.name == "404.html":
            continue
        h = f.read_text(encoding="utf-8", errors="replace")
        if 'http-equiv="refresh"' in h:
            continue
        # <head> の CSS や JSON-LD (script  blok) に字数を食われると割合が嘘を出す。
        # 人間が目に触れる本文だけを残して、そこから何割目で買えるか測る。
        b0 = h.find("<body")
        b0 = h.find(">", b0) + 1 if b0 >= 0 else h.find("</head>")
        b0 = b0 + 1 if b0 and b0 > 0 else 0
        body = h[b0:]
        import re as _re
        body = _re.sub(r"<script.*?</script>", "", body, flags=_re.S)
        body = _re.sub(r"<style.*?</style>", "", body, flags=_re.S)
        i = body.find("template=order.yml")
        rel = f.name if f.parent == ROOT else f.relative_to(ROOT).as_posix()
        if i < 0:
            out.append((rel, None, len(body)))
        else:
            out.append((rel, round(i / max(1, len(body)), 3), len(body)))
    return out


if __name__ == "__main__":
    polish()
    bad = [p for p in positions() if p[1] is None or p[1] > TOP_LIMIT]
    for rel, pos, n in positions():
        print(f"    {rel:26s} 注文欄 {('---' if pos is None else f'{pos * 100:5.1f}%')}  / {n:,} 字")
    if bad:
        print(f"  ★ 上部に注文欄が無い {len(bad)} 頁: {[b[0] for b in bad][:4]}")
        raise SystemExit(1)
    print("  上部の注文欄 全頁 OK")
