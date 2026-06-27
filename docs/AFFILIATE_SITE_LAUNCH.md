# 商品アフィリエイト導入サイト運用

作成日: 2026-06-25

## 目的

SNS投稿から受ける導入先として、比較サイト型の静的HTMLを作る。

最初はWordPressや有料サーバーを使わず、ローカルでHTMLを書き出す。公開先は後からGitHub Pages、WordPress、レンタルサーバーへ移せる。

## 現在できること

- トップページをHTML化
- カテゴリページをHTML化
- 比較ページ6本をHTML化
- 比較ページ下部に商品リンク枠を自動追加
- 楽天APIから商品候補を取得
- `status=active` かつ `affiliate_url` ありの商品だけ広告リンクとして表示
- 未承認・未登録リンクは「商品リンク準備中」と表示
- 広告表記、免責、編集方針ページを同梱

## サイト生成

```bash
cd /Users/matsumotokouki/Documents/あふぃ

python3 -m trend_commerce build-site --output output/site
```

生成先:

```text
output/site/index.html
```

## 商品リンクを追加する

ASPや楽天で実際のアフィリエイトリンクを取得してから、次の形で登録する。

```bash
python3 -m trend_commerce offer-add \
  --offer-id rakuten_portable_fan_001 \
  --network rakuten \
  --name "商品名" \
  --category "季節・暮らし" \
  --keyword "携帯扇風機" \
  --keyword "ハンディファン" \
  --problem-tag "外出暑さ対策" \
  --event-tag "猛暑" \
  --affiliate-url "取得したアフィリエイトURL" \
  --landing-url "通常の商品URL" \
  --reward-type percent \
  --reward-value 2 \
  --allowed-media site \
  --status active \
  --verified-at 2026-06-25
```

登録後、サイトを再生成する。

```bash
python3 -m trend_commerce build-site --output output/site
```

## 楽天APIの商品候補検索

楽天Web ServiceのAPIキーを `.env` に保存済みなら、次で商品候補を確認できる。

```bash
python3 -m trend_commerce rakuten-search \
  --keyword 携帯扇風機 \
  --limit 3
```

取得結果には、商品名、価格、レビュー数、レビュー平均、商品URL、アフィリエイトURL有無が含まれる。

APIキーは `.env` に保存し、Gitへ入れない。

## 楽天商品選定BOT

比較ページの商品枠ごとに、楽天APIで候補を集め、販売中・価格・レビュー数・レビュー平均・商品名一致・アフィリエイトURL有無でスコアリングする。

通常は楽天の商品カタログ検索ではなく、楽天市場の販売中商品検索を使う。販売中商品検索は `availability=1` を指定し、扱い終了の商品を避ける。

暑さ対策ページを選定して、候補CSVを書き出す。

```bash
python3 -m trend_commerce product-scout \
  --page-slug heat-relief-items-comparison \
  --limit-per-keyword 5 \
  --queries-per-group 2 \
  --delay-seconds 3 \
  --output output/products/heat_relief_rakuten_candidates.csv
```

最高スコア商品を `data/offers.csv` へ反映し、導入サイトも再生成する。

```bash
python3 -m trend_commerce product-scout \
  --page-slug heat-relief-items-comparison \
  --limit-per-keyword 5 \
  --queries-per-group 2 \
  --delay-seconds 3 \
  --output output/products/heat_relief_rakuten_candidates.csv \
  --activate \
  --build-site \
  --site-output output/site
```

速度制限を避けるため、`--delay-seconds` は短くしすぎない。

現在の初期スコア基準:

- アフィリエイトURLがある
- 楽天市場で販売中
- 価格が取得できる
- 商品タイプごとの需要に合いやすい価格帯
- レビュー数がある
- レビュー平均が高い
- レビュー数と評価が両立している
- 送料込み/送料無料
- 商品名が検索キーワード・商品カテゴリと一致する
- 中古、訳あり、商品タイプ違い、ペット用品混在などを減点する

誤選定が出たら、`trend_commerce/product_scout.py` の商品タイプ別除外ルールを追加してBOTを育てる。

## 商品リンクが表示される条件

`data/offers.csv` の対象行が次を満たすこと。

- `status` が `active`
- `affiliate_url` が空ではない
- 比較ページの商品候補と関連している

現状の比較ページ別候補は `data/comparison_product_map.csv` で管理する。

## 注意

- 取得していないアフィリエイトリンクを作ったふりで載せない
- 未使用商品を「使ってみた」と書かない
- 価格、在庫、仕様、保証はリンク先確認に寄せる
- アフィリエイトリンクには `rel="nofollow sponsored noopener"` を付ける
- SNSへ直接アフィリンクを貼るより、最初は比較ページへ送る

## 最初に入れるべき商品カテゴリ

1. 暑さ対策グッズ
2. 急速充電器
3. モバイルバッテリー
4. メンズスキンケア
5. 家トレ用品
6. AIツール

物販は報酬単価が低いので、まずはクリックが取りやすい季節商品・ガジェットで動線テストする。
