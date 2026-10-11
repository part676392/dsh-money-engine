"""面の先頭に注文欄を差し込む (最後の最後だけに有った為)。

実測: 注文欄の有る頁 7 枚すべてで、導線は本文の 77〜99% 目に在った。
      index.html は 145,446 字のうち 99% 目。上部には迂回 link だけ。
 builders は-pages を再生成する度に下書きし直すので、再生成の後に1回囀す所を別に持つ。
 money_check.cta_check が位置も点検する (上 25% 以内に注文の導線)。
"""
from __future__ import annotations

import pathlib
import re
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
        # 二度差しの禁止: h1 の直後に上部欄 (背景 #fff7e8) が有ればそれで足りる。
        # (実測で index.html の link が 3 -> 4 本に増えた。idempotent でなかった)
        h1i = h.find("</h1>")
        if h1i >= 0 and "fff7e8" in h[h1i:h1i + 900]:
            already.append(rel)
            continue
        # 重複した上部欄が残っていたら 1 個に畳む (手動再生成で 3 個積もった実測)
        n_bar = h.count("fff7e8")
        if n_bar > 1:
            first = h.index("fff7e8")
            cut = h.rindex("<p style=", 0, first)
            last_end = h.index("</p>", h.rindex("fff7e8")) + 4
            body_rest = h[last_end:]
            deduped = h[:cut] + h[cut:last_end].replace("</p></p>", "</p>")
            # 2 個目以降の <p ...fff7e8...</p> を落とす
            def drop_extra(txt):
                out, seen = [], 0
                i = 0
                while True:
                    j = txt.find("<p style=", i)
                    if j < 0:
                        out.append(txt[i:]); break
                    k = txt.find("</p>", j)
                    if k < 0:
                        out.append(txt[i:]); break
                    k += 4
                    seg = txt[j:k]
                    if "fff7e8" in seg:
                        seen += 1
                        if seen > 1:
                            i = k
                            continue
                    out.append(txt[i:j]); out.append(seg); i = k
                return "".join(out)
            h = drop_extra(h)
            f.write_text(h, encoding="utf-8")
            touched.append(rel + " (重複畳み)")
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


def visible_body(h: str) -> str:
    """CSS・JSON-LD を落とした『人間が読む本文』。文書全体の割合で測ると
    <style> や schema.org に字数を食われて嘘が出る (実測で es-deadlines が 86% 目扱い)。"""
    b0 = h.find("<body")
    b0 = h.find(">", b0) + 1 if b0 >= 0 else (h.find("</head>") + 1)
    body = h[b0 if b0 > 0 else 0:]
    body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
    return re.sub(r"<style.*?</style>", "", body, flags=re.S)


# 骨格で測る。実測: 上部欄を差した頁は全て </h1> の 272 字後に注文欄が来た。
GAP_LIMIT = 400          # </h1> から注文欄までの許容字数
H1_LIMIT = 1500          # 本文の先頭から h1 までの許容字数


def positions() -> list:
    """各頁で (rel, </h1> からの距離, h1 の本文先頭からの距離, 本文字数) を返す。"""
    out = []
    files = list(ROOT.glob("*.html")) + list((ROOT / "store").glob("*.html")) \
        + list((ROOT / "company").glob("*.html"))
    for f in files:
        if f.name == "404.html":
            continue
        h = f.read_text(encoding="utf-8", errors="replace")
        if 'http-equiv="refresh"' in h:
            continue
        rel = f.name if f.parent == ROOT else f.relative_to(ROOT).as_posix()
        body = visible_body(h)
        h1 = body.find("</h1>")
        oc = body.find("template=order.yml", h1 + 1) if h1 >= 0 else -1
        head_oc = body.find("template=order.yml")
        if h1 >= 0 and 0 <= head_oc < h1:        # h1 より上に在れば上出来
            out.append((rel, 0, h1, len(body)))
            continue
        if oc < 0:
            out.append((rel, None, h1, len(body)))
            continue
        out.append((rel, oc - h1, h1, len(body)))
    return out


if __name__ == "__main__":
    polish()
    rows = positions()
    bad = [r for r in rows if r[1] is None or r[1] > GAP_LIMIT] + \
          [r for r in rows if r[2] < 0 or r[2] > H1_LIMIT]
    for rel, gap, h1, n in rows[:6]:
        print(f"    {rel:34s} h1 @{h1:5d} / 注文欄 +{('---' if gap is None else str(gap)):>5s} 字 / 本文 {n:,} 字")
    if bad:
        print(f"  ★ 骨格が足りない {len(bad)} 頁: {[(b[0], b[1], b[2]) for b in bad[:3]]}")
        raise SystemExit(1)
    print(f"  上部の注文欄 全頁 OK ({len(rows)} 頁 / h1 から {max((r[1] or 0) for r in rows)} 字以内)")
