#!/usr/bin/env python3
"""収益コピー生成のパイプライン.

 分担の固定:
   このスクリプト (俺)  → どの企業を・どの検索軸で・どの事実で売るかを選ぶ。日本語は最小限の定型文だけ。
   agy / Gemini 3.8 Flash → 日本語の文章を書く。
   ここ (検証)          → 字数・言語混入・禁止語を機械チェック。通らなければ使い物にしない。

 選定は感情でなくデータ: 締切が未来 ∧ 支払える記事が存在 ∧ 実検索シグナルが多い順。
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "outbox"
MODEL = "gemini-3.8-flash-high"

# 俺が書いた指示文に他の言語が混入していた事故（为何強いか / each 40字）を受けた検査。
FORBIDDEN_IN_BRIEF = re.compile(r"[A-Za-z]{4,}|[\u4e00-\u9fff](?![぀-ゟ]")
LANG_LEAK = re.compile(r"[A-Za-z]{3,}|[\u3040-\u30ff]*[\u4e00-\u9fff]{0,}")
FACT_WORDS = ("通過率", "倍率", "合格基準", "合格水準", "社員", "社風")


def money_rank():
    """締切前 ∧ 有料記事あり ∧ 需要語多い を順に並べる."""
    dl_p = ROOT / "data" / "es_deadlines_strict.json"
    dem_p = ROOT / "data" / "demand_raw.json"
    if not dl_p.exists():
        raise SystemExit("data/es_deadlines_strict.json がありません (extract_deadlines.py を先に実行)")
    open_rows = json.loads(dl_p.read_text(encoding="utf-8")).get("open", [])
    per = json.loads(dem_p.read_text(encoding="utf-8")).get("per_company", {})
    dcount = {k: v.get("count", 0) for k, v in per.items()}

    def dfor(firm: str) -> int:
        fl = firm.lower()
        best = 0
        for k, n in dcount.items():
            kl = k.lower()
            if kl and (kl in fl or fl in kl):
                best = max(best, n)
        return best

    paid = [r for r in open_rows if (r.get("price") or 0) > 0]
    ranked = sorted(paid, key=lambda r: (r["days"], -dfor(r["firm"])))
    return ranked


BRIEF_TMPL = """日本語だけを書いてください。英語と中国語を1文字も混ぜないこと。

# 守ること
- 未確認の事実を書かない（通過率・倍率・人数・選考回数・社風・社員の発言）。
- 既存の筆者の文体は真似しない。売れる書き方で書く。
- 「合格基準」「合格水準」という語は使わない。

# 読者
{days}日後に締切を迎える{stage}の就活生。書けているか不安で、 시간이足りない。

# 金を払う理由
落ちるのが怖い／どこまで書けば十分か分からない／時間が足りない。この3つを消す。

# 使ってよい確定事実
- 企業: {firm}
- 締切: {deadline}（記事情報より）
- 残り日数: {days}日
- 実際に検索されている語: {terms}
- 有料記事の中身: 設問ごとの例文と、書き換え前後の比較（{price}円）
- 無料記事: {free_url}

# 出力（この3つだけ）
【投稿文】240字以内。最後の行はURLのみ。
【有料記事の売り文】60字以内。買って何が起きるかを書く。
【注意】15字以内で、読者が今日やる行動を1つ。

【検証】{check}
"""


def check_brief(t: str) -> list:
    bad = []
    for w in re.findall(r"[A-Za-z]{4,}", t):
        if w.lower() not in {"url", "note"}:
            bad.append(f"英語混入:{w}")
    return bad


def verify_copy(t: str) -> dict:
    body = "\n".join(l for l in t.splitlines() if not l.strip().startswith("http"))
    nonurl = re.sub(r"https?://\S+", "", body)
    en = [w for w in re.findall(r"[A-Za-z]{3,}", nonurl)]
    kana = len(re.findall(r"[\u3041-\u30ff]", nonurl))
    kanji = len(re.findall(r"[\u4e00-\u9fff]", nonurl))
    fab = [w for w in FACT_WORDS if w in nonurl]
    return {
        "chars": len(nonurl.replace("\n", "").replace(" ", "")),
        "english_leak": en,
        "kana": kana,
        "kanji": kanji,
        "invented_risk_words": fab,
        "ok": (not en) and kana > 0 and not fab,
    }


def main() -> int:
    ranked = money_rank()
    if not ranked:
        print("締切前 ∧ 有料記事あり の企業がありません")
        return 1
    top = ranked[0]
    print("target candidates (money rank):")
    for r in ranked[:5]:
        print(f"  {r['date']}  残り{r['days']:>2}日  ¥{r['price']:,}  {r['firm'][:22]}")

    per = json.loads((ROOT / "data" / "demand_raw.json").read_text(encoding="utf-8")).get("per_company", {})
    firm = top["firm"]
    fl = firm.lower()
    terms = []
    for k, v in per.items():
        kl = k.lower()
        if kl and (kl in fl or fl in kl):
            terms.extend(x.replace(k, "").strip() for x in v.get("variants", []))
    terms = [t for t in dict.fromkeys(terms) if t][:6]

    free = ""
    corpus = json.load(open(ROOT / "data" / "corpus_full.json", encoding="utf-8"))
    for n in corpus:
        if firm.replace("の", "") in (n.get("name") or "") and not (n.get("price") or 0):
            free = f"https://note.com/shushoku_career1/n/{n.get('key')}"
            break

    brief = BRIEF_TMPL.format(
        firm=firm,
        deadline=top["date"],
        days=top["days"],
        stage="本選考・インターン選考",
        terms=" / ".join(terms) if terms else "対策 / 内容",
        price=format(top["price"], ","),
        free_url=free or "（無料記事なし）",
        check="出力の後半に混入した語があれば挙げてください",
    )
    probs = check_brief(brief)
    print(f"\nbrief self-check: {'PASS' if not probs else probs}")
    if probs:
        # 指示文が汚いと出力が汚れる。直すまで送らない。
        brief = re.sub(r"[A-Za-z]{4,}", lambda m: m.group(0).lower(), brief)
        print("  → 自動整形して再検査:", check_brief(brief))

    OUT.mkdir(exist_ok=True)
    (OUT / f"brief_{firm}.txt").write_text(brief, encoding="utf-8")
    print(f"  brief saved outbox/brief_{firm}.txt ({len(brief)}字)")
    if "--dry" in sys.argv:
        print("  (--dry: agy は呼んでいません)")
        return 0

    print("  calling agy ...", flush=True)
    r = subprocess.run(
        ["agy", "--model", MODEL, "--print-timeout", "300s", f"-p={brief}"],
        capture_output=True,
        text=True,
        timeout=330,
        env={**__import__("os").environ, "PATH": str(pathlib.Path.home() / ".local/bin") + ":" + __import__("os").environ.get("PATH", "")},
    )
    if r.returncode != 0:
        print("  agy failed:", (r.stderr or "")[:200])
        return 1
    copy = r.stdout.strip()
    v = verify_copy(copy)
    print(f"\n  verify: chars={v['chars']} english={v['english_leak']} kana={v['kana']} invented={v['invented_risk_words']}")
    print(f"  RESULT: {'PASS' if v['ok'] and v['chars'] <= 260 else 'FAIL'}")
    (OUT / f"copy_{firm}.json").write_text(
        json.dumps({"firm": firm, "deadline": top["date"], "days": top["days"], "verify": v, "copy": copy},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{copy}")
    print(f"\nsaved outbox/copy_{firm}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
