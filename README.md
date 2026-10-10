# 中途・転職 面接対策 目録 (dsh-money-engine)

[![live](https://img.shields.io/badge/live-part676392.github.io-7a5230)](https://part676392.github.io/dsh-money-engine)

実測した「面接の情報」だけを積む静的データ資産。日本の転職・中途市場で、**検索が実際に発生している語**と**記事側に被覆が無い箇所**を突き続けています。

Live: https://part676392.github.io/dsh-money-engine ｜ 日本語のデータセットを AEO 向け（JSON-LD / FAQ / ItemList）に出しています。

## 入っているもの

| 内容 | 実測値 (2026-10-11) |
|---|---|
| 収容記事 | 600 本（note 公開API 由来） |
| 対象企業ページ | 491 ページ |
| 掲載金額の合計 | ¥1,205,920 |
| 選考ステージ別の締切 | 12 件（うち無料 6）根拠文つき |
| AI・録上面接の検索需要 | 23 社 / 34 語（autocomplete 機械収集） |
| 選考段階の言及 | 475 社 / 2,780 件（本文 HTML を直接取得して再抽出） |
| 面接質問の実文 | 472 社 / 1,873 問（質問＋記事が書く面接官の意図） |
| 公式選考フロー | 22 社 / 56 本（順序つき・寄せ前の工程名を保持） |

機械可読: [`data/snapshot-latest.json`](data/snapshot-latest.json) ／ 日別履歴: [`data/history/`](data/history/)

## 公開している頁

- [トップ（企業別ページの入口）](https://part676392.github.io/dsh-money-engine/)
- [運用履歴 — 観測系列の公開ログ](https://part676392.github.io/dsh-money-engine/changes.html)
- [AI・録上面接で検索されている企業 23 社](https://part676392.github.io/dsh-money-engine/ai-interviews.html)
- [選考締切一覧](https://part676392.github.io/dsh-money-engine/es-deadlines.html)
- [選考段階の言及 350 社・403 件（引用つき）](https://part676392.github.io/dsh-money-engine/selection-signals.html)
- [面接質問 1,873 問・472 社（面接官の意図つき）](https://part676392.github.io/dsh-money-engine/interview-questions.html)
- [公式選考フロー 56 本・22 社（順序つき）](https://part676392.github.io/dsh-money-engine/selection-flows.html)

提出済みの掲載申請: [okhosting/awesome-open-data#57](https://github.com/okhosting/awesome-open-data/pull/57) — `### Natural language` 節に1行。このリストは 2026-10-10 にも PR が merge されている (活性を確認してから出した)。巡回が `data/pr_watches.json` 経由で merge を監視する。
- [注文受付（カスタム執筆・暗号決済）](https://part676392.github.io/dsh-money-engine/store/)

## 正直な制約
- **権利の範囲を分けた**：CC BY 4.0 は抽出した表・順序・対応づけにのみ適用。本文の著作権は note の各記事の著者に帰属する。だから記事本文 (2,072,200字) はリポジトリに積まず、公開するのは各件 1 文の引用と出典URLまでに留めている。JSON-LD にも `creditText` と `isBasedOn` で明記した。

**索引されている証拠を、まだ持っていない。**

- **索引されていないことを、制御実験で確定した**（2026-10-11）。同じ計器で既知の語（`DeepSeek Harness`）を叩くと正しい結果が返る。その状態で `site:part676392.github.io` と固有語 4 本がすべて該当ゼロ＝計器の失明ではなく未索引。
- ただし Bing は**該当ゼロのときに無関係な頁を10件埋めてくる**（`site:` の検索で translate.google.com が並ぶ）。だから SERP の organic 件数を「索引済み件数」とは呼ばない。
- Google への sitemap ping は `404`、Bing の `/ping` は `410 Gone`。鍵なしで結果を退回できる計器がこの回線に無い。
- だから自前の访问計（abacus）を置いて、実ブラウザで +1 できることを確認したうえで、访问数を測っている。いまの访问数はほぼ自分の監査だ。
- AI 面接の出典を 23 社ぶん機械で探した結果、基準を満たしたのは **1 社だけ**（オムロン × VARIETAS、発表元はベンダー側）。ドメインの立派さだけで通した旧基準なら 37 件出ていたが、中身は商品サイトと株価ページだった。

## 支払いの通り道

| レール | 状態 |
|---|---|
| 暗号 (Base / Arbitrum / Polygon / Ethereum、1地址) | **開いている**。KYC なし・即金 |
| カード (Gumroad) | 垢・製品($6)・メール確認まで作成済み。**payout（銀行/PayPal）接続の一段だけ人間が必要** → [購入口](https://gumroad.com/l/bopcg) は "not currently for sale" 中 |
| Ko-fi / Qiita | Cloudflare Turnstile / hCaptcha が登録を止めている |
| Hacker News | 登録を試みると "account creation disabled" が返る（開閉を刻々切り替えている）。監視中に開けばそのまま垢を取る |

詳細: [PAYMENT_RAILS.md](PAYMENT_RAILS.md)

## 無人運用

macOS `launchd`（06:10 / 19:40）から [`daily_loop.sh`](daily_loop.sh) が 14 工程を回す：締切更新 → 頁生成 → 配布面の生存 → 访问 read-back → 受金残高 → 受信箱 → 得点盤 → 履歴生成 → push → IndexNow。

`launchd` に渡される PATH に `gh` が無く **push が毎朝静かに失敗していた**故障を、同一環境を再現して見つけて直した実績がある。だから「動くはず」で止めずに、同じ環境で通すまでを成果数えている。

## この repo の約束

推定と見込みを本文に書かない。取れた文書と再取得できる数値だけを出す。壊れた計器は失敗欄ではなく失敗欄に記録する。
