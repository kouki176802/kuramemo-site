# 検索流入の実装方針

## 実装済み

- ページ固有の title と meta description
- 公開URL設定時の canonical URL
- Article / CollectionPage / BreadcrumbList のJSON-LD
- 大きな画像プレビューを許可する robots meta
- 公開URL設定時の sitemap.xml と robots.txt
- 商品画像の代替テキスト
- カテゴリから比較ページ、比較ページから関連ガイドへの内部リンク
- 国、媒体、話題の理由、確認日、楽天順位を表示する話題根拠欄
- スマホ375px幅で全34ページの横はみ出し、画像切れ、見出し切れを検査

比較ページは複数商品を扱うため、単一商品向けの Product 構造化データを付けない。価格やレビューは楽天の取得値として画面に表示し、サイト自身のレビューだと見せない。

## 公開時に必要

1. HTTPSの公開URLを `SITE_BASE_URL` に設定
2. サイトを再生成
3. Search Console確認トークンを設定
4. sitemap.xml をSearch Consoleへ送信
5. 代表ページをURL検査し、リッチリザルトテストも実施

## 2026-07-03 公開サイト確認

- `https://kuramemo-mk.com/` は200で応答
- robots.txtはクロールを許可
- sitemap.xmlは公開済み
- wwwは非wwwへ301転送
- トップのcanonicalとサイトマップURLを `https://kuramemo-mk.com/` に統一

## Search Consoleで行う作業

1. `kuramemo-mk.com` をドメインプロパティとして登録
2. お名前.com DNSへGoogle指定のTXTレコードを追加
3. `https://kuramemo-mk.com/sitemap.xml` を送信
4. URL検査で `https://kuramemo-mk.com/` を確認
5. 「インデックス登録をリクエスト」を実行
6. 次に主要カテゴリと注目商品の代表ページを数件だけリクエスト

サイトマップ送信は発見を助けますが、掲載や順位を保証するものではありません。内容が薄い候補一覧だけのページを増やさず、検索意図ごとに比較軸と個別説明を追加します。

ローカル表示中は誤って検索登録されないよう noindex と robots.txt の拒否を維持する。

## 2026-07-10 追加でURL検査するページ

専門性を強めたページから優先して、Search ConsoleのURL検査で登録リクエストする。

1. `https://kuramemo-mk.com/category-food.html`
   - 狙い: 食・宅食カテゴリの入口
   - 検索意図: 宅食、冷凍弁当、時短ごはん、食事管理
2. `https://kuramemo-mk.com/meal-delivery-comparison.html`
   - 狙い: 宅食・冷凍弁当の専門比較ページ
   - 検索意図: 宅食 おすすめ、冷凍弁当 比較、一人暮らし 宅食、時短ごはん
3. `https://kuramemo-mk.com/category-housework-timesaving.html`
   - 狙い: 家事・時短の専門カテゴリ
   - 検索意図: 時短家電、家事ラク、共働き 家電、一人暮らし 家電
4. `https://kuramemo-mk.com/internet-line-services.html`
   - 狙い: サービス系の専門比較ページ
   - 検索意図: 光回線 比較、インターネット回線 おすすめ、戸建て 回線、マンション 回線

URL検査の直後に検索順位が出るわけではない。まずはクロールされる状態にし、2〜4週間はSearch Consoleの「ページ」「検索パフォーマンス」で表示回数の有無を見る。

## 公式資料

- Google 検索セントラル「有用で信頼性の高いユーザー第一のコンテンツ」
  - https://developers.google.com/search/docs/fundamentals/creating-helpful-content
- Google 検索セントラル「商品スニペットの構造化データ」
  - https://developers.google.com/search/docs/appearance/structured-data/product-snippet?hl=ja
- Google 検索セントラル「サイトマップの作成と送信」
  - https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap?hl=ja
