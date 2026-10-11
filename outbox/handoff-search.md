# 人間の指紋を 1 回だけ借りたい（約 5 分・費用 0 円）

状況の実測: 現金 $0 / 受信箱 0 件 / 検索エンジンに出ている私の頁 **0 面**
(bing site: 0 面、DuckDuckGo 0、Google 0)。IndexNow の送信は 200 が返っているので
「投げていない」ではなく「認識されていない」。ここだけは機械で代替できません。

## A. Bing Webmaster Tools（先にこちら / 索引が速い）
1. https://www.bing.com/webmasters に Microsoft アカウントでログイン
2. 「Add site」→ URL に `https://part676392.github.io/dsh-money-engine/` を入力
3. 検証方法に **HTML file** を選ぶと `BingSiteAuth.xml` のような **ファイル名と中身の 1 行**が出る
4. **そのファイル名と中身をこのチャットに貼るだけ**（銀行情報・契約なし）
5. 私が自動で: リポジトリに置いて push → sitemap.xml を送信 → 毎巡回で「索引された面数」を実測

## B. Google Search Console（索引の実数にはこちらが要る）
1. https://search.google.com/search-console/about → 「Start now」→ Google アカウントでログイン
2. プロパティ型は **URL prefix**、`https://part676392.github.io/dsh-money-engine/`
3. 所有権の確認 → **HTML file** を選ぶと `googleXXXXXXXXXXXX.html` が 1 個出る
4. その **ファイル名と中身をチャットに貼るだけ**
5. 私が sitemap を Pages に置いて送信、以後「索入室センサー」が実数を数えます
   （今は `IndexNow getstatus` が 404 で本数が測れていません。GSC が来れば数字になります）

## C. 任意（できたら助かる / 別の日で良い）
- Gumroad の受取設定を接続 → カード決済の口が開く（今は正直に「カードはまだ用意できていません」と出していています）
- https://github.com/part676392/dsh-money-engine/discussions/new?category=announcements
  に `outbox/discussion-first-post.md` の内容を貼って投稿（GitHub の UI からだと 1 分。API からは作れませんでした）

## 貼ってくれた後の自動処理（私がやること）
- `check_seo_verification.py` が「未取得 → 検証ファイル生きている」に切り替わり、
  壊れたら巡回が ★ を出す
- 索引された面数は `check_index_probe.py` が毎巡回で実測（現状 0 面）。0 のままでも嘘にならないのが主眼
- 費用 0 円、契約・法的リスクは発生させません（ファイル 1 個の公開だけ）
