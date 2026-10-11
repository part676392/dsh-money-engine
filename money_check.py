#!/usr/bin/env python3
"""金銭ページ (store/, store/mini.html) の受注に必要な物が揃っているか守る.

 動機: 先に自分の probe が '$' しか探さず、mini の '3 USD' 表記を見落とした。
 値札・送り先・支払い段取り・語数の段のどれか一つでも欠けると、
 読者は買いたくても買えない。だから毎巡回で実 HTML を引き直して検査する。

 検査するもの (全部 生きた HTTP 応答に対して):
   1. 価格 (\\$6 か "6 USD" かの両方を受け取る)
   2. 送り先メール (受信箱 address)
   3. 暗号 address (0x...)
   4. 支払いの順序が読める ("pay" と "email"/"send" の両方)
   5. 語数の段が parser の TIERS と一致する
"""
from __future__ import annotations

import collections
import html
import json
import pathlib
import re
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent
BASE = "https://part676392.github.io/dsh-money-engine"
PAGES = ["store/", "store/mini.html"]


def tiers() -> dict:
    src = (ROOT / "check_orders.py").read_text(encoding="utf-8")
    m = re.search(r"TIERS = (\{[^}]+\})", src)
    return eval(m.group(1)) if m else {}


def data_prices() -> dict:
    """データ資産頁の値札を code 側から読む。頁と突合してズレを赤にする。"""
    src = (ROOT / "build_dataset_store.py").read_text(encoding="utf-8")
    m = re.search(r"TIER = \[(.*?)\]\n", src, re.S)
    tiers = []
    if m:
        for nums in re.findall(r"\((\d+),\s*(\d+)\)", m.group(1)):
            tiers.append(int(nums[1]))
    h = re.search(r"HISTORY_USD = (\d+)", src)
    hist = int(h.group(1)) if h else 0
    return {"prices": sorted(set(tiers + ([hist] if hist else []))), "n_offers": len(tiers) + (1 if hist else 0)}


def fetch(p: str) -> str:
    r = subprocess.run(["curl", "-s", "--max-time", "25", f"{BASE}/{p}"],
                       capture_output=True, text=True, timeout=32)
    return r.stdout


def has_price(text: str, usd: int) -> bool:
    return bool(re.search(rf"\$\s?{usd}\b", text) or re.search(rf"\b{usd}\s*(?:USD|usd|ドル)", text))


def history_pub_check() -> bool:
    """頁に書いた「観測 N 件」と CSV 行数と history file 数は一致していなければならない。
    1,873/1,779 の失敗と同じ形 (公称と納品がズレる) を历史でも許さない。"""
    import re as _re
    files = [f for f in (ROOT / "data" / "history").glob("*.json") if f.name != "index.json"]
    fp = ROOT / "exports" / "history_timeseries.csv"
    csv_rows = 0
    if fp.exists():
        with open(fp, encoding="utf_8_sig") as f:
            csv_rows = max(sum(1 for _ in f) - 1, 0)
    page = (ROOT / "data-license.html").read_text(encoding="utf-8", errors="replace")
    m = _re.search(r"今積んでいる観測\s*<b>([0-9,]+)</b>", page)
    claimed = int(m.group(1).replace(",", "")) if m else -1
    ok = claimed == csv_rows == len(files) and claimed > 0
    print(f"    history publish: 頁={claimed} CSV={csv_rows} file={len(files)} "
          f"{'一致' if ok else '★ 不一致'}")
    return ok


def issue_form_check() -> bool:
    """GitHub の注文フォーム (.github/ISSUE_TEMPLATE/order.yml) の契約検査。
    YAML lib が無い環境なので、issue form に必要な形だけを構文として見る
    (壊れると GitHub は無言で blank form に落ちる = 注文が取りこぼれる)。"""
    fp = ROOT / ".github" / "ISSUE_TEMPLATE" / "order.yml"
    if not fp.exists():
        print("    issue form       : ★ file が無い")
        return False
    raw = fp.read_text(encoding="utf-8")
    lines = [l for l in raw.split("\n") if l.strip() and not l.strip().startswith("#")]
    top = [l.split(":")[0] for l in lines if not l.startswith((" ", "-"))]
    need_top = [k for k in ("name", "description", "body") if k not in top]
    types = re.findall(r"^[ \t]*(?:-[ \t]+)?type:[ \t]+([a-z]+)", raw, re.M)
    bad_type = [t for t in types if t not in ("markdown", "textarea", "input", "dropdown", "checkboxes")]
    n_label = len(re.findall(r"^[ \t]+label:", raw, re.M))
    n_opt = len(re.findall(r"^[ \t]+options:", raw, re.M))
    n_req = len(re.findall(r"required: true", raw))
    # dropdown には options, input/textarea には label が必須
    n_drop = len(re.findall(r"^[ \t]*(?:-[ \t]+)?type:[ \t]+dropdown", raw, re.M))
    n_text = len(re.findall(r"^[ \t]*(?:-[ \t]+)?type:[ \t]+(?:input|textarea)", raw, re.M))
    ok = (not need_top) and (not bad_type) and n_drop <= n_opt and n_text <= n_label
    print(f"    issue form       : {'OK' if ok else '★'}  top={top} fields={len(types)}"
          f" dropdown={n_drop}/options={n_opt} input系={n_text}/label={n_label} required={n_req}"
          + (f"  欠け={need_top or []} 不正type={bad_type}" if not ok else ""))
    return ok


def qcount_check() -> bool:
    """公称の質問数と納品 CSV の行数は同じでなければならない。
    実測で 1,873 (公称) / 1,779 (CSV) の差が出ていた。頁に旧値が残っても検査は落ちていなかったので、頁まで含めて総点検する。"""
    import csv as _csv
    j = json.loads((ROOT / "data" / "interview_questions.json").read_text(encoding="utf-8"))
    rows = 0
    fp = ROOT / "exports" / "interview_questions.csv"
    if fp.exists():
        with open(fp, encoding="utf_8_sig") as f:
            rows = max(sum(1 for _ in f) - 1, 0)
    body = sum(len(v) for v in (j.get("per_company") or {}).values())
    total = int(j.get("questions_total", -1))
    ok = total == body == rows
    # 同じ数を頁に写している箇所を総点検。1 か所でも旧値が残ると買い手に嘘を見せる。
    stale = []
    for fp in sorted(list(ROOT.glob("*.html")) + list(ROOT.glob("*.txt"))):
        raw = fp.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"面接質問\s*([0-9][0-9,]*)\s*問", raw):
            v = int(m.group(1).replace(",", ""))
            if v not in (total, 105):  # 105 は見本の3社ぶん (別個体)
                stale.append(f"{fp.name}:{v}")
    ok = ok and not stale
    print(f"    question count   : 公称={total} JSON本文={body} CSV={rows} "
          f"{'一致' if not stale else '★ 頁に旧値 ' + str(stale[:3])}")
    return ok


def profile_check(live_text=None) -> bool:
    """GitHub プロフィール頁 (part676392/part676392) の数字がこちら再生成と一致しているか。
    raw.githubusercontent は CDN で 1 分ほど古い値を返す実測があるので API で読む。
    プロフィールは目録の顔。そこに古い数字 (491社 / 1,779 問) が残ると全部の信用が落ちる。"""
    import base64
    import build_profile_readme as BP
    # 制御試験では live の写しを渡せる (本物の profile を壊さずに ★ を出せる)。
    if live_text is not None:
        return _profile_audit(live_text)
    try:
        out = subprocess.run(["gh", "api", f"repos/{BP.OWNER_REPO}/contents/README.md",
                             "--jq", ".content"], capture_output=True, text=True, timeout=90)
    except Exception as e:  # noqa: BLE001
        print(f"    profile 頁        : 読み飛ばし ({str(e)[:40]})")
        return True
    if out.returncode != 0:
        print("    profile 頁        : 読めない (token scope?) ので省略")
        return True
    live = base64.b64decode(out.stdout.strip()).decode("utf-8", "replace")
    return _profile_audit(live)


def _profile_audit(live: str) -> bool:
    import build_profile_readme as BP
    # 再生成したものと突合すると、巡回の途中で 実行背骨 の行数が増えるので、
    # 生成の瞬間差で ★ になる (10:24 実測)。 committed した生成物と突合する。
    if BP.LOCAL.exists():
        loc = BP.LOCAL.read_text(encoding="utf-8")
        i0 = loc.find(BP.MARK)
        want = loc[i0:] if i0 >= 0 else ""
        src_name = "data/profile_readme.md"
    else:
        want = BP.section()
        src_name = "再生成した節"
    i = live.find(BP.MARK)
    sec_live = live[i:] if i >= 0 else ""
    bad = []
    if not sec_live:
        bad.append("データ資産 の節が無い")
    else:
        # 数字だけを # に丸めて比べる。実行背骨の行数と観測件数だけ箱で違う
        # (runner は push のたびに積む) が、URL・文・価格は一字一句同じでないといけない。
        dig = lambda t: re.sub(r"[0-9][0-9,.,]*", "#", t)
        # 行の集合で比べる。部分文字列で当たると link を落としても通ってしまう (制御で実測)。
        live_lines = {dig(l.strip()) for l in sec_live.splitlines() if len(l.strip()) > 12}
        for line in want.split("\n"):
            ln = line.strip()
            if len(ln) <= 12:
                continue
            if dig(ln) not in live_lines:
                bad.append(f"live に無い行 ({src_name}): {ln[:56]}")
                break
    n_link = sec_live.count("src=prof")
    if n_link < 4:
        bad.append(f"計測 link が {n_link} 本しかない")
    for pat, why in ((r"1,873\s*問", "raw 抽出値を問で公称"), (r"491\s*社", "束ねる前の社数")):
        if re.search(pat, sec_live):
            bad.append(why)
    # 数字は CSV から組み直して live に要求する。生成物同士の比較は箱の時刻で揺れるが、
    # CSV は merge 后同じなので「live が古い数を公称していない」を正直に測れる。
    try:
        import csv as _csv
        import io as _io

        def _rows(name):
            with _io.open(ROOT / "exports" / name, encoding="utf_8_sig") as fh:
                return list(_csv.DictReader(fh))

        q = _rows("interview_questions.csv")
        lu = _rows("question_lineups.csv")
        fl = _rows("selection_flows.csv")
        sg = _rows("selection_signals.csv")
        dist = len({(r.get("question") or "").strip() for r in q if (r.get("question") or "").strip()})
        pages = sum(1 for f in (ROOT / "company").glob("*.html")
                    if 'http-equiv="refresh"' not in f.read_text(encoding="utf-8", errors="replace"))
        must = [f"面接質問 **{len(q):,} 行（重複を除いた実文 {dist:,} 文）**",
                f"質問カテゴリの並び順 **{len(lu):,} 行**",
                f"公式選考フロー **{len(fl):,} 行**",
                f"段階への言及 **{len(sg):,} 行**",
                f"企業別の頁 **{pages:,} 枚**"]
        for m in must:
            if m not in sec_live:
                bad.append(f"live が実dataと違う数を公称: {m} が無い")
    except Exception as e:  # noqa: BLE001
        print(f"      (数字の突合は省略: {str(e)[:44]})")
    ok = not bad
    print(f"    profile 頁        : {'OK' if ok else '★ ' + '; '.join(bad[:2])}"
          f"  (live {len(sec_live):,}字・計測 link {n_link} 本)")
    return ok


def cta_check() -> bool:
    """人間が着く面に注文欄が在るか。
    実測: index.html は访问 17 件で注文 link 0 / 羅列 5 件で 0 / store 4 件で 0。
    買う場所を探す人に買う場所が無かった。link・価格・GitHub アカウントの注意を点検する。"""
    import urllib.parse
    tpl_f = ROOT / ".github" / "ISSUE_TEMPLATE" / "order.yml"
    if not tpl_f.exists():
        print("    面の注文欄      : ★ order.yml が無い")
        return False
    tpl = tpl_f.read_text(encoding="utf-8")
    opts = [ln.split("- ", 1)[1].strip() for ln in tpl.split("\n") if ln.strip().startswith("- ")]
    pages = [p for p in list(ROOT.glob("*.html")) + list((ROOT / "store").glob("*.html"))
             if p.name != "404.html"]
    bad = []
    for f in pages:
        h = f.read_text(encoding="utf-8", errors="replace")
        if 'http-equiv="refresh"' in h:      # 別名の連絡頁は本体へ誘導すれば十分
            continue
        rel = f.name if f.parent == ROOT else f"store/{f.name}"
        hrefs = (re.findall(r"href='([^']*template=order\.yml[^']*)'", h)
                 + re.findall(r'href="([^"]*template=order\.yml[^"]*)"', h))
        if not hrefs:
            bad.append(f"{rel} に注文 link が無い")
            continue
        if "$5" not in h:
            bad.append(f"{rel} が価格 ($5) を出していない")
        if "注文には GitHub のアカウント" not in h:
            bad.append(f"{rel} に GitHub アカウントの注意が無い")
        for u in hrefs:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(u.replace("&amp;", "&")).query)
            for plan in q.get("plan", []):
                if plan not in opts:
                    bad.append(f"{rel} の plan「{plan[:20]}」が form の選択肢に無い")
    ok = not bad
    print(f"    面の注文欄      : {'OK' if ok else '★ ' + '; '.join(bad[:3])}"
          f"  ({len(pages)} 頁を点検)")
    return ok


def prefill_check() -> bool:
    """注文 link の prefill が form の仕様と合っているか。
    GitHub は field の `id` を query key に使う (公式仕样)。id や選択肢の文字列が動くと、
    配った link は黙って空欄で開く。企業頁 473 枚の link を全部機械で開いて確かめる。"""
    import urllib.parse
    tpl_f = ROOT / ".github" / "ISSUE_TEMPLATE" / "order.yml"
    if not tpl_f.exists():
        print("    order prefill     : ★ order.yml が無い")
        return False
    tpl = tpl_f.read_text(encoding="utf-8")
    ids = re.findall(r"^\s*id:\s*([A-Za-z0-9_-]+)", tpl, re.M)
    opts = [l.split("- ", 1)[1].strip() for l in tpl.split("\n")
            if re.match(r"^\s+- .*\(\$\d+\)\s*$", l)]
    snap = json.loads((ROOT / "data" / "snapshot-latest.json").read_text(encoding="utf-8"))
    n_comp = int(snap.get("companies") or 0)
    bad, nbad, n_cta, n_beacon = [], [], 0, 0
    for need in ("plan", "companies"):
        if need not in ids:
            bad.append(f"form に id `{need}` が無い {ids}")
    if n_comp and f"{n_comp}社" not in tpl:
        bad.append(f"form が現在の企業数 {n_comp}社 を書いていない (古い数字で売っている)")
    cdir = ROOT / "company"
    for f in sorted(cdir.glob("*.html")):
        h = f.read_text(encoding="utf-8", errors="replace")
        if 'http-equiv="refresh"' in h:
            continue
        m = re.search(r"class='buy' href='([^']+)'", h)
        if not m:
            nbad.append(f.name[:-5][:14] + " (CTA 無し)")
            continue
        n_cta += 1
        if "order-click" not in h:
            nbad.append(f.name[:-5][:14] + " (click beacon 無し)")
        u = html.unescape(m.group(1))
        q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
        extra = sorted(set(q) - ({"template", "title", "labels"} | set(ids)))
        if extra:
            nbad.append(f"{f.name[:-5][:10]} key {extra}")
            continue
        if q.get("template") != ["order.yml"]:
            nbad.append(f"{f.name[:-5][:10]} template 違い")
        if (q.get("plan") or [""])[0] not in opts:
            nbad.append(f"{f.name[:-5][:10]} plan が選択肢に無い")
        if (q.get("companies") or [""])[0] != f.name[:-5]:
            nbad.append(f"{f.name[:-5][:10]} companies 違い")
    if nbad:
        bad.append(f"link 不全 {len(nbad)} 頁 {nbad[:2]}")
    # 注文に GitHub のアカウントが要ることを隠さない (未ログインだと /login に飛ぶと実測した)。
    dl = (ROOT / "data-license.html").read_text(encoding="utf-8", errors="replace")
    if "GitHub のアカウント" not in dl:
        bad.append("data-license に GitHub アカウントの注意が無い")
    acct = 0
    for f in cdir.glob("*.html"):
        h = f.read_text(encoding="utf-8", errors="replace")
        if "class='buy'" in h:
            acct += 1
            if "GitHub のアカウント" not in h:
                bad.append(f"{f.name[:-5][:12]} に注意書きが無い")
                break
    ok = not bad
    print(f"    order prefill     : {'OK' if ok else '★ ' + '; '.join(bad[:2])}"
          f"  (CTA {n_cta} 頁・注意書き {acct} 頁・form の id {ids}・選択肢 {len(opts)} 個)")
    return ok


def company_identity_check() -> bool:
    """同じ会社の頁が2枚並んでいないか。束ねた古い名前は連絡頁 (noindex + canonical + 転送) にする。
    実測: 統合前は JR西日本が4頁、先頭が全角スペースの名前が8件あった (491 頁 / 実体 479 社)。"""
    from company_names import token_key
    cdir = ROOT / "data"
    cdir = ROOT / "company"
    if not cdir.exists():
        print("    company identity  : ★ company/ が無い")
        return False
    live = []
    groups = collections.defaultdict(list)
    redir, bad = 0, []
    for f in sorted(cdir.glob("*.html")):
        n = f.name[:-5]
        h = f.read_text(encoding="utf-8", errors="replace")
        if 'http-equiv="refresh"' in h:
            redir += 1
            if 'content="noindex' not in h:
                bad.append(f"連絡頁 {n[:14]} に noindex が無い")
            if 'rel="canonical"' not in h:
                bad.append(f"連絡頁 {n[:14]} に canonical が無い")
            continue
        live.append(n)
        groups[token_key(n)].append(n)
        if n != n.strip() or n.startswith("\u3000"):
            bad.append(f"全角スペース付きの名前が本体頁のまま {n[:16]}")
    split = {k: v for k, v in groups.items() if len(v) > 1}
    if split:
        bad.append(f"同じ会社が分裂 {list(split.values())[:2]}")
    idx = (ROOT / "index.html").read_text(encoding="utf-8", errors="replace")
    ok = not bad
    print(f"    company identity  : {'OK' if ok else '★ ' + '; '.join(bad[:2])}"
          f"  (本体 {len(live):,} 頁・連絡頁 {redir} 頁・分裂 {len(split)})")
    return ok


def company_q_check() -> bool:
    """企業頁が質問実文を持っているか。実文の無い会社は空欄を正直に出す。
    実測: 実文 1,779 行 / 472 社、企業頁 491 頁。 pages に載る期待値を data から計算して突合する。"""
    j = json.loads((ROOT / "data" / "interview_questions.json").read_text(encoding="utf-8"))
    per = j.get("per_company") or {}
    cdir = ROOT / "company"
    if not cdir.exists():
        print("    company pages     : ★ company/ が無い")
        return False
    files = {f.name: f for f in cdir.glob("*.html")}
    have, miss, q_miss, empty_ok, empty_bad, faq = [], [], [], 0, [], 0
    from company_names import canon_map
    cm, _al = canon_map(list(per) + list(files))
    # 名前ゆれを束ねたので、頁は canonical ぶん、質問は束ねた後ろぶんが載る。
    merged = collections.defaultdict(list)
    for comp, v in per.items():
        merged[cm.get(comp, comp)].extend(v)
    for comp, v in merged.items():
        f = files.get(comp + ".html")
        if f is None:
            continue
        h = f.read_text(encoding="utf-8", errors="replace")
        if "面接で投げられた質問の実文" not in h:
            miss.append(comp)
            continue
        have.append(comp)
        # escape の形 (&quot; など) に左右されず、人が読む本文で突合する
        txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))
        uniq = [re.sub(r"\s+", " ", (r.get("question") or "").strip())[:40] for r in v]
        uniq = [u for u in dict.fromkeys(uniq) if u]
        need = min(3, len(uniq))
        got = sum(1 for u in uniq if u in txt)
        if got < need:
            q_miss.append(f"{comp} (頁 {got}/{need})")
        faq += h.count("と聞かれますか？")
    for name, f in files.items():
        comp = name[:-5]
        h0 = f.read_text(encoding="utf-8", errors="replace")
        if 'http-equiv="refresh"' in h0:
            continue      # 束ねた古い名前の連絡頁なので空欄の説明は要らない
        if cm.get(comp, comp) in merged:
            continue
        h = f.read_text(encoding="utf-8", errors="replace")
        if "まだ収録できていません" in h:
            empty_ok += 1
        elif "面接で投げられた質問の実文" not in h:
            empty_bad.append(name)
    # 道しるべ CSV が頁の実在とズレていないか (build_site より先に作ると前の回の枚数で出る)。
    import csv as _csv
    cpc = ROOT / "exports" / "company_pages.csv"
    stale = []
    if not cpc.exists():
        bad.append("company_pages.csv が無い")
    else:
        with open(cpc, encoding="utf_8_sig") as fh:
            for r in _csv.DictReader(fh):
                nm = r.get("company") or ""
                ck = cm.get(nm, nm)
                want = 1 if (cdir / (ck + ".html")).exists() else 0
                got = 1 if (r.get("page_exists") or "") == "1" else 0
                if want != got:
                    stale.append(nm[:14])

    on_pages = len([c for c in merged if c + ".html" in files])
    bad = []
    if len(have) != on_pages:
        bad.append(f"実文ブロック {len(have)} 頁 / 期待 {on_pages} 頁 欠け {[m[:18] for m in miss[:3]]}")
    if stale:
        bad.append(f"company_pages.csv が頁の実在と食い違う {len(stale)} 行 {stale[:2]}")
    if q_miss:
        bad.append(f"頁に載った実文が data と違う {len(q_miss)} 頁 {[m[:16] for m in q_miss[:2]]}")
    if empty_bad:
        bad.append(f"実文の無い会社で空欄の説明が無い {empty_bad[:3]}")
    ok = not bad
    print(f"    company questions : {'OK' if ok else '★ ' + '; '.join(bad[:2])}"
          f"  ({len(have)}/{on_pages} 頁に実文・空欄の説明 {empty_ok} 頁・FAQ実文Q&A {faq:,} 件)")
    return ok


def qmeta_check() -> bool:
    """行と実文の二つの数が、頁・JSON・CSV で揃っているか。
    実測: 1,779 行のうち 500 行が同一文。延べ数だけ載せると『1,779問ある』嘘になる。"""
    import csv as _csv
    j = json.loads((ROOT / "data" / "interview_questions.json").read_text(encoding="utf-8"))
    total = int(j.get("questions_total") or -1)
    dist = int(j.get("questions_distinct_text") or -1)
    cf = j.get("category_frequency") or {}
    bad = []
    if sum(cf.values()) != total:
        bad.append(f"category_frequency 計 {sum(cf.values())} != 行数 {total}")
    cov = sum(v for k, v in cf.items() if k != "未判定")
    if total and cov * 100 / total < 55:
        bad.append(f"分類被打率 {cov * 100 // total}% が下限 55% 未満")
    fp = ROOT / "exports" / "interview_questions.csv"
    if not fp.exists():
        bad.append("interview_questions.csv が無い")
    else:
        with open(fp, encoding="utf_8_sig") as f:
            rd = _csv.DictReader(f)
            cols = rd.fieldnames or []
            need = ["category", "category_basis", "question_raw"]
            miss = [c for c in need if c not in cols]
            if miss:
                bad.append(f"CSV 列が無い {miss}")
            else:
                cc = collections.Counter()
                nrow = 0
                for r in rd:
                    nrow += 1
                    cc[r.get("category") or "無印"] += 1
                if nrow != total:
                    bad.append(f"CSV {nrow} 行 != JSON {total}")
                for k, v in cf.items():
                    if cc.get(k, 0) != v:
                        bad.append(f"CSV の {k}={cc.get(k,0)} != JSON {v}")
    # 頁側の公称: 行の数は total、実文の数は dist でなければならない
    stale_row, stale_dist = [], []
    for f2 in sorted(list(ROOT.glob("*.html")) + list(ROOT.glob("*.txt"))):
        raw = f2.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"面接質問\s*([0-9][0-9,]*)\s*(問|行)", raw):
            v = int(m.group(1).replace(",", ""))
            if v not in (total, 105):
                stale_row.append(f"{f2.name}:{v}")
        for m in re.finditer(r"実文\s*([0-9][0-9,]{2,})", raw):
            v = int(m.group(1).replace(",", ""))
            if v not in (dist, 105):
                stale_dist.append(f"{f2.name}:{v}")
    if stale_row:
        bad.append(f"頁に旧行数 {stale_row[:3]}")
    if stale_dist:
        bad.append(f"頁に旧実文数 {stale_dist[:3]}")
    # README は generated 扱いではない (再生成されない)。ここだけ古い数字が残った実測がある。
    rd = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""
    if rd:
        raw_r = int(j.get("questions_extracted_raw") or 0)
        want = f"{total:,} 行（重複を除いた実文 {dist:,} 文）"
        if want not in rd:
            bad.append(f"README に 「{want}」 が無い")
        if raw_r and f"{raw_r:,} 問" in rd:
            bad.append(f"README が raw 抽出値 {raw_r:,} 問 を公称")

    ok = not bad
    print(f"    row / 実文 / 分類   : {'OK' if ok else '★ ' + '; '.join(bad[:3])}"
          f"  (行 {total:,}・実文 {dist:,}・分類被打 {cov:,}・被打率 "
          f"{cov * 100 // total if total else 0}%)")
    return ok


def outreach_check() -> bool:
    """外に出した文面 (open PR) が、こちらの公開数字とズレていないか。
    PR の側は自分で再生成できないので、読み直すしかない。
    実測で両 PR が raw 抽出値 1,873 を公称にし、#57 だけ stage 言及を 2,780 (CSV は 2,021) と書いていた。"""
    f = ROOT / "data" / "outreach.json"
    if not f.exists():
        print("    outreach rails    : 台帳が無いので省略")
        return True
    rails = json.loads(f.read_text(encoding="utf-8")).get("rails") or []
    j = json.loads((ROOT / "data" / "interview_questions.json").read_text(encoding="utf-8"))
    nq = int(j.get("questions_total") or -1)
    raw = int(j.get("questions_extracted_raw") or -2)
    sig = 0
    sf = ROOT / "exports" / "selection_signals.csv"
    if sf.exists():
        with open(sf, encoding="utf_8_sig") as fh:
            sig = max(sum(1 for _ in fh) - 1, 0)
    bad = []
    for r in rails:
        repo, num = r["repo"], r["pr"]
        out = subprocess.run(["gh", "api", f"repos/{repo}/pulls/{num}"],
                             capture_output=True, text=True, timeout=60)
        try:
            d = json.loads(out.stdout)
        except Exception:  # noqa: BLE001
            bad.append(f"#{num} が読めない")
            continue
        body = d.get("body") or ""
        # comment も読む (本文を直しても comment が古い数字を残していた実測がある)。
        cms = []
        co = subprocess.run(["gh", "api", f"repos/{repo}/issues/{num}/comments",
                             "--jq", '[.[] | select(.user.login == "part676392") | .body]'],
                            capture_output=True, text=True, timeout=60)
        try:
            cms = json.loads(co.stdout or "[]")
        except Exception:  # noqa: BLE001
            bad.append(f"#{num} comment が読めない")
        if d.get("state") != "open":
            bad.append(f"#{num} state={d.get('state')} (閉結・併合なら台帳を更新)")
            continue
        if f"{nq:,}" not in body:
            bad.append(f"#{num} に公開質問数 {nq:,} が無い")
        if f"{raw:,} interview questions" in body:
            bad.append(f"#{num} が raw 抽出値 {raw:,} を質問数として公称")
        # 「N 問」で行数と実文を混ぜない (行 / 実文 を併記した文だけ通す)。
        qpat = re.compile(r"[0-9,]{3,}\s*問")
        for i, text in enumerate(cms):
            if f"{raw:,} interview questions" in text:
                bad.append(f"#{num} comment{i + 1} が raw 抽出値 {raw:,} を質問数として公称")
            for m in qpat.finditer(text):
                span = text[max(0, m.start() - 60):m.end() + 60]
                if "重複を除いた実文" not in span:
                    bad.append(f"#{num} comment{i + 1} が「{m.group(0)}」を実文と分けずに公称")
                    break
        if sig and f"{sig:,}" not in body:
            bad.append(f"#{num} の stage 言及が CSV 行数 {sig:,} で無い")
    ok = not bad
    print(f"    outreach 文面      : {'OK' if ok else '★ ' + '; '.join(bad[:3])}"
          f"  ({len(rails)} 先 / 質問 {nq:,}・stage {sig:,})")
    return ok


def not_found_check() -> bool:
    """迷った人を目録と値段に戻せるか。GitHub 既定の 404 だと資産の名前も $5 も消える。
    ステータスコードは 404 のままにする (嘘の 200 にしない)。"""
    bogus = "kesson-page-" + str(int(time.time())) + ".html"
    r = subprocess.run(["curl", "-s", "--max-time", "25", "-w", "\n@@%{http_code}",
                        f"{BASE}/{bogus}"], capture_output=True, text=True, timeout=40)
    out = r.stdout or ""
    code = out.rsplit("@@", 1)[-1].strip() if "@@" in out else "?"
    body = out.rsplit("\n@@", 1)[0] if "\n@@" in out else out
    need = {
        "自有の404": "その頁は見つかりません" in body,
        "値段の入口": "1社だけ $5" in body,
        "目録へのlink": "interview-questions.html" in body,
        "noindex": 'content="noindex' in body,
        "访问計": 'fetch(b+"404"' in body,
    }
    ok = code == "404" and all(need.values())
    print(f"  404 の受け皿       : {'OK' if ok else '★'}  HTTP {code}  "
          + " ".join(f"{k}:{'o' if v else '×'}" for k, v in need.items()))
    return ok


def main() -> int:
    tr = tiers()
    inbox = ""
    wfile = ROOT / "outbox" / "mailtm.json"
    addr = ""
    if wfile.exists():
        inbox = json.loads(wfile.read_text(encoding="utf-8")).get("address", "")
    wfile2 = ROOT / "outbox" / "wallet.json"
    if wfile2.exists():
        addr = json.loads(wfile2.read_text(encoding="utf-8")).get("address", "")
    rows = []
    all_ok = True
    for p in PAGES:
        raw = fetch(p)
        text = re.sub(r"<[^>]+>", " ", raw)
        t = re.sub(r"\s+", " ", text)
        prices = sorted({int(x) for x in re.findall(r"\$\s?(\d{1,2})\b", t)} |
                        {int(x) for x in re.findall(r"\b(\d{1,2})\s*(?:USD|usd)\b", t)} |
                        {int(x) for x in re.findall(r"\b(\d{1,2})\s*ドル", t)})
        checks = {
            "bytes": len(raw),
            "prices": prices,
            "inbox": bool(inbox) and inbox in t,
            "wallet": bool(addr) and addr in t,
            "how_to_pay": bool(re.search(r"\b(pay|送金)\b", t, re.I)) and
                          bool(re.search(r"\b(email|send|注文)\b", t, re.I)),
            "words_stated": bool(re.search(r"\b\d{1},?\d{3}\s*(?:words|word|語)", t)),
        }
        # parser の段が公開頁のどこかに全部出ているか (mini 側に来ているので合算で見る)
        rows.append((p, checks))
        if len(raw) < 2000:
            print(f"  ★ {p}: 応答が短い ({len(raw)}B) — 配信事故の可能性")
            all_ok = False
        if not checks["inbox"] or not checks["wallet"]:
            print(f"  ★ {p}: 送り先が足りない inbox={checks['inbox']} wallet={checks['wallet']}")
            all_ok = False
    # 段の突合は全頁合わせて
    joined = " ".join(re.sub(r"<[^>]+>", " ", fetch(p)) for p in PAGES)
    missing = [f"{w}→${v}" for w, v in tr.items() if not has_price(joined, v)]
    if missing:
        print(f"  ★ parser の段が公開頁に無い: {', '.join(missing)}")
        all_ok = False
    print(f"  checked at {time.strftime('%Y-%m-%d %H:%M:%S')}  pages={len(PAGES)}")
    for p, c in rows:
        print(f"    {p:16s} {c['bytes']:>6,}B  prices={c['prices']} inbox={c['inbox']} "
              f"wallet={c['wallet']} pay_steps={c['how_to_pay']} words={c['words_stated']}")
    # --- データ資産の販売頁 (値札は code から読んで突合) ---
    exp = data_prices()
    raw = fetch("data-license.html")
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))
    got = sorted({int(x) for x in re.findall(r"\$\s?(\d{1,3})\b", t)})
    miss = [p_ for p_ in exp["prices"] if p_ not in got]
    ld_ok, n_off = False, 0
    for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', raw, re.S):
        try:
            d = json.loads(blk)
        except Exception:
            continue
        if d.get("@type") == "Service":
            n_off = len(d.get("offers") or [])
            ld_ok = bool(d.get("name")) and n_off > 0
    d_checks = {"bytes": len(raw), "prices_on_page": got, "prices_missing": miss,
                "inbox": bool(inbox) and inbox in t, "wallet": bool(addr) and addr in t,
                "ld_service_offers": ld_ok, "offers": n_off,
                "delivery_is_url": ("公開URL" in t),
                "no_mail_delivery_claim": ("メールで送ります" not in t),
                "rights_bodies_excluded": ("本文は納品物に入れません" in t)}
    print(f"    data-license.html {len(raw):>6,}B  prices={got} offers={n_off} "
          f"inbox={d_checks['inbox']} wallet={d_checks['wallet']} "
          f"納品=URL:{d_checks['delivery_is_url']} 権利明記:{d_checks['rights_bodies_excluded']}")
    if len(raw) < 2000:
        print(f"  ★ data-license.html: 応答が短い ({len(raw)}B)")
        all_ok = False
    if miss:
        print(f"  ★ 値札が公開頁に無い: {miss} (code 側 {exp['prices']})")
        all_ok = False
    if exp["n_offers"] != n_off:
        print(f"  ★ Offer の数がズレ: code={exp['n_offers']} 頁={n_off}")
        all_ok = False
    if not ld_ok:
        print("  ★ Service 構造化データが name/offers を欠く")
        all_ok = False
    if not d_checks["delivery_is_url"] or not d_checks["no_mail_delivery_claim"]:
        print("  ★ 納品形の記述が嘘つきかけ (外送信できないのにメール送信と書いていないか)")
        all_ok = False
    if not d_checks["rights_bodies_excluded"]:
        print("  ★ 本文を同梱しない旨が頁から消えた")
        all_ok = False

    # --- 納品一覧 (約束した納品形が実在するか) ---
    raw = fetch("deliveries.html")
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))
    n_rows = len(re.findall(r"<tr><td><code>", raw))
    empty_ok = "受注はまだ 0 件です" in raw
    ld_ok = False
    for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', raw, re.S):
        try:
            d = json.loads(blk)
        except Exception:
            continue
        me = d.get("mainEntity") or {}
        ld_ok = d.get("@type") == "ItemPage" and me.get("@type") == "ItemList" and \
                "itemListElement" in me
    back = ("data-license.html" in raw) and ("store/" in raw) and ("sample.html" in raw)
    # 反向: 販売頁と目録がここを指しているか (孤児頁を許さない)
    dl = fetch("data-license.html")
    idx = fetch("")
    from_here = ("deliveries.html" in dl, "deliveries.html" in idx)
    print(f"    deliveries.html {len(raw):>6,}B  行={n_rows} 空状態={empty_ok} "
          f"JSON-LD={ld_ok} 出口link={back}  seller/index→here={from_here}")
    d_checks = {"bytes": len(raw), "rows": n_rows, "empty_state": empty_ok,
                "ld_itemlist": ld_ok, "out_links": back, "linked_from": list(from_here)}
    if len(raw) < 1200:
        print(f"  ★ deliveries.html: 応答が短い ({len(raw)}B) — 未 deploy か配信事故")
        all_ok = False
    if n_rows == 0 and not empty_ok:
        print("  ★ deliveries.html: 行も無く空状態の文も無い (何を書いた頁か不明)")
        all_ok = False
    if not ld_ok:
        print("  ★ deliveries.html: ItemPage/ItemList 構造化データが足りない")
        all_ok = False
    if not back:
        print("  ★ deliveries.html: 注文の入口への link が無い (行き止まり)")
        all_ok = False
    if not all(from_here):
        print(f"  ★ deliveries.html: 販売頁/目録から呼べていない {from_here}")
        all_ok = False

    # --- 納品物見本 (買 vật that が品物を見られるか) ---
    raw = fetch("sample.html")
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))
    csv_link = "exports/sample_dossier.csv" in raw
    cta = "data-license.html" in raw
    n_q = len(re.findall(r"<tr><td>\d+</td>", raw))
    ld_ok = False
    for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', raw, re.S):
        try:
            d = json.loads(blk)
        except Exception:
            continue
        me = d.get("mainEntity") or {}
        ld_ok = d.get("@type") == "ItemPage" and me.get("@type") == "Dataset" and \
                bool(me.get("name")) and bool(me.get("description"))
    s_checks = {"bytes": len(raw), "question_rows": n_q, "csv_link": csv_link,
                "cta_to_license": cta, "ld_itempage_dataset": ld_ok}
    print(f"    sample.html {len(raw):>6,}B  質問行={n_q} CSVlink={csv_link} "
          f"購入頁link={cta} JSON-LD={ld_ok}")
    if len(raw) < 3000:
        print(f"  ★ sample.html: 応答が短い ({len(raw)}B) — 配信事故か未 deploy")
        all_ok = False
    if n_q < 20:
        print(f"  ★ sample.html: 質問行が少なすぎる ({n_q})。見本として成立しない")
        all_ok = False
    if not csv_link:
        print("  ★ sample.html: 納品物 CSV への link が無い")
        all_ok = False
    if not cta:
        print("  ★ sample.html: 購入頁への link が無い (見本で終わって売れない)")
        all_ok = False
    if not ld_ok:
        print("  ★ sample.html: ItemPage/Dataset 構造化データが足りない")
        all_ok = False
    # CSV が実際に降るか (link だけあって 404 の古典を塞ぐ)
    r = subprocess.run(["curl", "-s", "--max-time", "25", f"{BASE}/exports/sample_dossier.csv"],
                       capture_output=True, text=True, timeout=40)
    body = r.stdout.lstrip("\ufeff")
    head = body.split("\n", 1)[0]
    lines = len([x for x in body.split("\n") if x.strip()])
    is_csv = head.startswith("company,record_type,")
    print(f"    sample_dossier.csv: 行数={lines} BOM={r.stdout.startswith(chr(65279))} "
          f"先頭行={head[:44]!r}")
    if not is_csv:
        # 404 の HTML が行数だけ満たして通る古典 (実測: 404 が 74 行だった)
        print(f"  ★ sample_dossier.csv: CSV として読めない (先頭行が違う) — 404 の可能性")
        all_ok = False
    elif lines < 50:
        print(f"  ★ sample_dossier.csv が小さい ({lines} 行)")
        all_ok = False

    print(f"  parser tiers: {tr}")
    print(f"  公開価格の突合: {'PASS' if not missing else 'FAIL ' + str(missing)}")
    if not qcount_check():
        all_ok = False
    if not history_pub_check():
        all_ok = False
    if not issue_form_check():
        all_ok = False
    if not profile_check():
        all_ok = False
    if not prefill_check():
        all_ok = False
    if not company_identity_check():
        all_ok = False
    if not company_q_check():
        all_ok = False
    if not qmeta_check():
        all_ok = False
    if not outreach_check():
        all_ok = False
    if not not_found_check():
        all_ok = False
    if not cta_check():
        all_ok = False
    print(f"\n  money pages ready: {all_ok}")
    out = ROOT / "data" / "rails" / "money_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                              "sample_page": s_checks,
                              "deliveries_page": d_checks,
                              "dataset_page": d_checks,
                              "pages": dict(rows), "parser_tiers": tr,
                              "missing_tiers": missing, "ready": all_ok},
                             ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
