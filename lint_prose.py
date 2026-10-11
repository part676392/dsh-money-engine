#!/usr/bin/env python3
"""日本語の文中に ASCII の語が動詞として混ざっていないか洗う。

 実測: 「管線が物を-create できる」が納品頁に実在した (2026-10-11)。
 毎回直すよう言われているのに目視で通り過ぎているので、code に番をさせる。
"""
from __future__ import annotations

import html
import pathlib
import re
ROOTS = pathlib.Path(".")

# 助詞の直後に ASCII 語が来て、そのまま活用している形を拾う。
PARTICLE = "(を|が|は|に|で|と|も|まで|らを)"
SEP = "[-「」‘’〔]?"
WORD = "([A-Za-z][A-Za-z_\\-']{3,})"
VERB = "(する|します|できる|出来ます|した|して|される|したい|してみる)"
BAD_HINT = re.compile(PARTICLE + r"\s*" + SEP + r"\s*" + WORD + r"\s*" + SEP + r"\s*" + VERB)

ALLOW = set("""html http https json csv url urls css dom api spec by cc dsh money engine
rehearsal deliverable word words dataset datasets index sitemap github git dev runner
create work ok err sha token note com org img src href alt span div meta fallback
generated publish shelf strike point value image files count input output""".split())


# 簡体字専用の字形 (日本語の表記には出ない)。実測で混入していた物を含む:
#   訪問 (check_traffic ほか 19 所 / changes.html に 4 所), 仕様 (order_link.py 3 所)
# 0x6CA1 (没) と 0x88CF (裏) は日本語で使うので入れていない (実測: 「裏打ちされた動機」が
# 誤検知した)。簡体字側にしかない字形だけを code point で固定する。
SIMPLIFIED = "".join(chr(c) for c in (0x8BBF, 0x95EE, 0x6837, 0x540E, 0x5F55, 0x89C2,
                     0x8BB0, 0x8FD8, 0x672F, 0x8BA9, 0x8FDE, 0x95E8, 0x53D1, 0x8FD0,
                     0x5173, 0x8F6C, 0x91CA, 0x6781, 0x663E, 0x5904))
SIMPL_RE = re.compile("[" + SIMPLIFIED + "]")


def scan_simplified(path: pathlib.Path) -> list:
    """日本語の本文将簡体字が紛れ込んでいないか (自分の log 文も洗う)。"""
    raw = path.read_text(encoding="utf-8", errors="replace")
    txt = html.unescape(re.sub(r"<[^>]+>", " ", raw)) if path.suffix == ".html" else raw
    out = []
    for m in SIMPL_RE.finditer(txt):
        ctx = txt[max(0, m.start() - 16):m.start() + 16].replace("\n", " ")
        out.append((m.group(0), ctx))
    return out


def scan(path: pathlib.Path) -> list:
    raw = path.read_text(encoding="utf-8", errors="replace")
    txt = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    txt = re.sub(r"\s+", " ", txt)
    hits = []
    for m in BAD_HINT.finditer(txt):
        w = m.group(2)   # 2 番が ASCII 語。3 番は助動詞なので allow list が効かない
        if w.lower() in ALLOW:
            continue
        hits.append((w, txt[max(0, m.start() - 16):m.end() + 12].strip()))
    return hits


FOREIGN = re.compile(r"[\u0400-\u04ff\u0600-\u06ff\u0370-\u03ff\u0e00-\u0e7f\uac00-\ud7af]")


def scan_scripts(path: pathlib.Path) -> list:
    """日本語の code/頁に异国文字が紛れ込んだ実測を2件、ここで拾う。"""
    raw = path.read_text(encoding="utf-8", errors="replace")
    hits = []
    for i, line in enumerate(raw.split("\n"), 1):
        for m in FOREIGN.finditer(line):
            hits.append((i, m.group(0), line.strip()[:66]))
    return hits


def main() -> int:
    root = pathlib.Path(".")
    files = (sorted(root.glob("*.html")) + sorted((root / "store").glob("*.html"))
             + sorted((root / "deliveries").glob("*.html"))
             + sorted(root.glob("company/*.html")))[:600]
    total = 0
    bad_files = 0
    scripts = [p for p in sorted(ROOTS.glob("*.py"))]
    for f in scripts:
        for ln, ch, txt in scan_scripts(f)[:2]:
            print(f"  ★ {f.name}:{ln} 异国文字 '{ch}' → {txt}")
            total += 1
    # 簡体字は日本語の漢字と区別が付きにくいので別枠で数える (訪問 / 仕様 の実測)
    simp = 0
    for f in scripts + files:
        for ch, ctx in scan_simplified(f)[:2]:
            print(f"  ★ {f.name}: 簡体字 '{ch}' → …{ctx}…")
            simp += 1
        if simp >= 12:
            break
    total += simp
    for f in files:
        hits = scan(f)
        if hits:
            bad_files += 1
            total += len(hits)
            for w, ctx in hits[:3]:
                print(f"  ★ {f.name}: '{w}' → …{ctx}…")
        if bad_files >= 8:
            break
    print(f"  対象 {len(files)} 頁 / 混入 {total} 件 ({bad_files} 頁)"
          + (f" / 簡体字 {simp} 件" if simp else ""))
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
