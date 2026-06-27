# 日次運用ランブック

作成日: 2026-06-25

## 目的

登録・課金前は、BOTを完全自動投稿させず、ローカルで投稿案と記事案を作り、手動投稿で反応を確認する。

## 毎日やること

### 1. トレンド収集

```bash
python3 -m trend_commerce collect
```

### 2. 記事・SNS案生成

```bash
python3 -m trend_commerce run
```

### 3. SNSキュー確認

```bash
python3 -m trend_commerce social-queue
```

### 4. 投稿案を承認

初期は全承認せず、目視でよいものだけ承認する。

```bash
python3 -m trend_commerce social-approve --id 1
```

まとめて承認する場合:

```bash
python3 -m trend_commerce social-approve --all
```

### 5. 手動投稿用CSV出力

```bash
python3 -m trend_commerce social-export --file output/social/manual_posts.csv
```

### 5.5 手動テスト投稿CSVをBOTキューへ入れる

X手動投稿テスト用CSVをDBキューへ取り込む。

```bash
python3 -m trend_commerce social-import \
  --file samples/social/x_bot_test_posts.csv \
  --platform x \
  --approve
```

取り込み後、未投稿キューを確認する。

```bash
python3 -m trend_commerce social-queue --platform x --status ready
```

CSVへ出す。

```bash
python3 -m trend_commerce social-export \
  --file output/social/x_ready_queue.csv \
  --platform x
```

手動投稿した後は、DBキューを公開済みにする。

```bash
python3 -m trend_commerce social-mark-published \
  --id 2 \
  --permalink https://x.com/m0506k/status/POST_ID
```

### 6. SNSへ手動投稿

API契約前はCSVを見ながら手動投稿する。

優先:

1. X
2. Threads
3. Instagram

TikTokは動画なし方針なので台本保存のみ。

### 7. 反応を記録

投稿後、数時間〜翌日に以下へ記録する。

`data/manual_metrics_template.csv`

見る指標:

- 表示回数
- いいね
- 返信
- リポスト
- 保存
- プロフィールクリック
- リンククリック

## 週1でやること

### 1. 投稿テーマを見直す

反応がよかったテーマを確認。

- AIツール
- 急速充電器
- モバイルバッテリー
- メンズスキンケア
- 家トレ用品
- 暑さ対策

### 2. 比較ページを更新

反応があったSNS投稿から、比較ページへ追記する。

例:

- よくクリックされた投稿 → 比較ページの冒頭に反映
- 返信で聞かれたこと → FAQへ追加
- 保存されたInstagram案 → チェックリスト化

### 3. 商品候補を見直す

`data/comparison_product_map.csv` を見て、次に実商品名を調べる候補を決める。

### 4. CEOレポート生成

```bash
python3 -m trend_commerce report
```

## 投稿数の目安

### 初期2週間

- X: 1日1〜2本
- Threads: 1日1本
- Instagram: 週2本
- TikTok: 台本のみ

### 反応確認後

- X: 1日2〜3本
- Threads: 1日1〜2本
- Instagram: 週3本

## 投稿優先順位

1. 比較ページへ送れる投稿
2. 保存されやすいチェックリスト投稿
3. 用途別・条件別ランキング投稿
4. トレンドに絡めた短文投稿
5. 商品単体の紹介

商品単体紹介は、ASP承認・広告表記・SNS掲載可否が確認できるまで後回し。

ランキング投稿は、報酬順ではなく「初心者向け」「軽さ重視」「省スペース重視」など条件別にする。

## 信頼導線の配分

初期は以下の比率を目安にする。

- 認知投稿: 30%
- 信頼投稿: 30%
- 比較投稿: 30%
- 行動投稿: 10%

毎日リンク投稿ばかりにしない。まず「このアカウントは比較の視点が役に立つ」と思ってもらう。

## 停止条件

次に該当したら投稿を止める。

- 広告表記がない
- 実リンクが未確認
- 健康効果や収益効果を断定している
- 災害・事故・事件を購買誘導に使っている
- 同じ投稿を重複している
- 炎上・スキャンダルに便乗している
- 商品情報が古い可能性がある

## 今日やるなら

1. `data/social_accounts_template.csv` にSNS URLを入れる
2. SNSプロフィール文を反映する
3. `samples/social/30_post_manual_test_plan.md` から3本投稿する
4. 投稿URLを `data/manual_metrics_template.csv` に記録する
5. 翌日、反応を入力する

## 現在のX半自動化状態

- Xアカウント: https://x.com/m0506k
- 固定投稿: 済み
- BOTテスト投稿: 2本投稿済み
- 未投稿readyキュー: `output/social/x_ready_queue.csv`
- 投稿後は `social-mark-published` でDB側も更新する
