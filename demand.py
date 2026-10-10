#!/usr/bin/env python3
"""検索需要 (Google autocomplete) をサイトに出すための部品.

 сайтыの既存 block には手を入れず、需要レイヤだけを後付けする。
 力が要る箇所は「人々が実際に何と検索しているか」を FAQPage 構造化データに
 変換するところで、これにより AI Overview / Google が実質問を引用できる。
"""
from __future__ import annotations

import json
import pathlib
import re
from urllib.parse import quote

DATA = pathlib.Path(__file__).resolve().parent / "data"

# 検索されている語を話題ごとに束ねる。求職者の実際の不安軸で分ける。
THEME_AXES = [
    # データを見て作り直した順。「その他」45% の中身を確認したら
    # 選考ステージ指定と AI/録上面接が混ざっていたため分離した。
    ("選考ステージ指定", ("中途", "最終", "一次", "二次", "二 次", "1次", "2次", "役員", "中途採用", "転職", "インターン")),
    ("通過・落ちる", ("通過", "落ちた", "落ちる", "落ち", "不採用", "基準", "ボーダー")),
    ("結果・連絡", ("結果", "連絡", "いつ", "遅い", "来ない", "届か", "日程", "合否")),
    ("倍率・回数", ("倍率", "回数", "何回", "何 回", "1回", "何次", "人数", "何人")),
    ("準備・中身", ("対策", "質問", "準備", "答え", "聞く", "聞か", "内容", "プレゼン", "ケース", "流れ", "フロー")),
    ("AI・録上面接", ("ai", "録画", "動画", "nonvoice", "自動翻訳")),
    ("雇用形態", ("パート", "契約社員", "期間工", "バイト", "アルバイト", "高校生", "正社員", "派遣")),
    ("服装・持ち物", ("服装", "私服", "スーツ", "持ち物", "カバン", "交通費", "ネクタイ")),
    ("圧迫・雰囲気", ("圧迫", "キツイ", "厳し", "優しい", "きつい", "雰囲気")),
    ("語学", ("英語", "英会話", "語学")),
    ("給与・条件", ("給料", "年収", "給与", "待遇", "条件", "残業")),
]


def load() -> dict | None:
    p = DATA / "demand_raw.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def axis_of(term: str) -> str:
    for name, keys in THEME_AXES:
        for k in keys:
            if isinstance(k, str) and k.lower() in term.lower():
                return name
    return "その他"


def company_variants(comp: str, demand: dict) -> list:
    """need clean_company'd key fallback: demand keyed by cleaned name."""
    per = demand.get("per_company", {})
    hit = per.get(comp)
    if hit:
        return hit.get("variants", [])
    for k, v in per.items():
        if k and (k in comp or comp in k):
            return v.get("variants", [])
    return []


def themes_block(demand: dict, by_company: dict) -> str:
    """index 用の需要パネル: 記事が答えている軸 vs 実際に搜かれている軸."""
    per = demand.get("per_company", {})
    with_demand = {k: v for k, v in per.items() if v.get("count", 0) > 0}
    axis_count = {}
    example = {}
    for comp, v in with_demand.items():
        for var in v.get("variants", []):
            # autocomplete は大文字小文字を崩す (AGC -> agc)。無視して剥がさないと
            # 会社名が残ったままになり 47% が「その他」に落ちた。
            tail = var
            for pat in (comp, "面接", "es", "ES"):
                tail = re.sub(re.escape(pat), " ", tail, flags=re.I)
            tail = re.sub(r"\s+", " ", tail).strip(" ・,、")
            if not tail:
                continue
            a = axis_of(tail)
            axis_count[a] = axis_count.get(a, 0) + 1
            example.setdefault(a, var)

    total_terms = sum(len(v.get("variants", [])) for v in with_demand.values())
    ordered = sorted(axis_count.items(), key=lambda x: -x[1])

    lis = []
    for a, n in ordered:
        pct = n / max(total_terms, 1) * 100
        ex = example.get(a, "")
        lis.append(
            "<li><b>%s</b> <span class='pc'>%d語 / %.0f%%</span>"
            "<span class='ex'>例: %s</span></li>" % (a, n, pct, ex[:40])
        )

    coverage = len(with_demand) / max(len(per), 1) * 100
    return (
        "<div class='demand'><h2>🔎 求職者が実際に検索していること"
        " <small>%d社 / %d語（需要シグナルあり %d社 = %.0f%%）</small></h2>"
        "<ul>%s</ul>"
        "<p class='gap'>この目録の資料は「聞かれる質問と回答例」を中心に集めています。"
        "ただ上の一覧を見ると、搜かれているのは <b>一次・最終どの段階の話か／結果はいつ届くのか／通過率は何%か</b>"
        " という疑問の方が多い。当社録の各企業ページでも、この三段階・結果・通過率までの記載はまだ薄い。"
        "更新の優先順位はここから決めていきます。</p></div>"
        % (
            len(per),
            total_terms,
            len(with_demand),
            coverage,
            "".join(lis),
            (ordered[0][0] if ordered else "通過・落ちる"),
        )
    )


def company_block(comp: str, demand: dict) -> str:
    v = company_variants(comp, demand)
    if not v:
        return (
            "<div class='nod'><b>この企業の検索需要はまだ観測されません。</b> "
            "<span>= 競合が薄い。先に押さえた者が見つかる。</span></div>"
        )
    items = "".join(
        "<li><a href='https://www.google.com/search?q=%s'>%s</a>"
        "<span class='ax'>%s</span></li>" % (quote(x), x, axis_of(x.replace(comp, "").strip()))
        for x in v
    )
    return (
        "<div class='demand'><h2>🔎 「%s 面接」で実際に入力されている検索語</h2>"
        "<ul>%s</ul></div>" % (comp, items)
    )


def company_ld(comp: str, demand: dict, base_ld: dict) -> dict:
    """実検索語を FAQPage の Q&A に変えて構造化データに足す."""
    v = company_variants(comp, demand)
    if not v:
        return base_ld
    extra = []
    for q in v:
        extra.append(
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": (
                        "%s の選考について検索されている語です。"
                        "対策資料は %s を参照。" % (comp, "%s の面接対策資料")
                    ),
                },
            }
        )
    merged = dict(base_ld)
    merged["mainEntity"] = list(base_ld.get("mainEntity", [])) + extra
    return merged


def dump_for_site(demand: dict, by_company: dict, out_dir: pathlib.Path) -> None:
    """需要データも snapshot / history に載せて「後から取れない」を証明できるようにする."""
    per = demand.get("per_company", {})
    slim = {
        "harvested_at": demand.get("harvested_at"),
        "source": demand.get("source"),
        "companies_probed": demand.get("companies_probed"),
        "companies_with_demand": demand.get("companies_with_demand"),
        "question_themes": demand.get("question_themes", [])[:30],
        "top_companies_by_demand": sorted(
            ((k, v.get("count", 0)) for k, v in per.items()), key=lambda x: -x[1]
        )[:40],
    }
    (out_dir / "data" / "demand-latest.json").write_text(
        json.dumps(slim, ensure_ascii=False, indent=1), encoding="utf-8"
    )
