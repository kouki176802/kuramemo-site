# 残り作業用URL集

作成日: 2026-06-25

## 目的

登録、規約確認、API接続、公開準備で使う公式URLをまとめる。

ログイン、登録、契約、APIキー発行はCEO作業。パスワードは共有しない。

## 優先度A: まず使う

### 楽天アフィリエイト

- はじめ方: https://affiliate.rakuten.co.jp/guides/begin/
- サイト情報の登録: https://affiliate.rakuten.co.jp/
- ガイドライン: https://affiliate.rakuten.co.jp/guideline/rule/

用途:

- 初期の物販候補
- 季節・暮らし
- ガジェット周辺機器
- メンズ美容
- 家トレ用品

確認すること:

- 公開SNSが登録されているか
- 商品リンクの作成方法
- SNS掲載可否
- 成果条件

### もしもアフィリエイト

- 公式: https://af.moshimo.com/
- 利用規約: https://af.moshimo.com/af/www/terms/shop

用途:

- 物販導線
- Amazon / 楽天 / Yahoo系の比較導線
- 初期比較ページの商品候補

確認すること:

- 登録媒体
- 案件ごとのSNS掲載可否
- Amazon提携の申請タイミング

### A8.net

- 公式: https://www.a8.net/
- メディア会員利用規約: https://support.a8.net/as/terms.html

用途:

- 美容
- フィットネス
- サブスク
- SaaS
- 将来のスクール・転職系

確認すること:

- 案件ごとの禁止表現
- SNS掲載可否
- 成果条件
- 否認条件

### バリューコマース

- 公式: https://www.valuecommerce.ne.jp/affiliate/
- 利用規約: https://www.valuecommerce.ne.jp/st_affiliate/terms.html

用途:

- 大手EC
- 通販
- ガジェット
- 将来のサービス比較

確認すること:

- サイト審査
- 登録媒体
- 案件ごとのSNS掲載可否

## 優先度B: サイト公開後

### Search Console URL検査

- トップ: https://kuramemo-mk.com/
- サイトマップ: https://kuramemo-mk.com/sitemap.xml
- 食・宅食カテゴリ: https://kuramemo-mk.com/category-food.html
- 宅食・冷凍弁当比較: https://kuramemo-mk.com/meal-delivery-comparison.html
- 家事・時短カテゴリ: https://kuramemo-mk.com/category-housework-timesaving.html
- 光回線比較: https://kuramemo-mk.com/internet-line-services.html

用途:

- Search ConsoleのURL検査
- ASP登録時の媒体URL
- SNSプロフィールや固定投稿のリンク確認

### Amazonアソシエイト

- 公式: https://affiliate.amazon.co.jp/
- 紹介料率: https://affiliate.amazon.co.jp/welcome/compensation
- 運営規約: https://affiliate.amazon.co.jp/help/operating/agreement
- プログラムポリシー: https://affiliate.amazon.co.jp/help/operating/policies

用途:

- ガジェット
- 生活用品
- 書籍
- 日用品

注意:

- 空サイトで急がない
- 180日以内の一定売上・審査条件を確認
- SNS利用条件を確認
- 有料広告・ブースト投稿からの誘導条件に注意

### WordPress

- WordPress.org: https://wordpress.org/download/
- WordPressドキュメント: https://wordpress.org/documentation/
- WordPress開発者向けREST API: https://developer.wordpress.org/rest-api/

用途:

- 比較ページ公開
- 固定ページ公開
- WordPress下書き投稿BOT接続

確認すること:

- サーバー契約
- ドメイン
- WordPress URL
- 投稿専用ユーザー
- アプリケーションパスワード

### サーバー・ドメイン候補

候補:

- Xserver: https://www.xserver.ne.jp/
- ConoHa WING: https://www.conoha.jp/wing/
- さくらのレンタルサーバ: https://rs.sakura.ad.jp/
- お名前.com: https://www.onamae.com/

注意:

- 最初は月1,000〜2,000円程度に抑える
- WordPress簡単インストールがあるものを優先
- 自動バックアップとSSL対応を確認

## 優先度C: BOT自動化・API

### OpenAI API

- API料金: https://openai.com/api/pricing/
- APIドキュメント: https://platform.openai.com/docs
- APIキー管理: https://platform.openai.com/api-keys
- 使用量確認: https://platform.openai.com/usage

用途:

- 記事生成品質向上
- タイトル案
- メタディスクリプション
- SNS投稿生成
- 比較表の補助

注意:

- 月額上限を決める
- 最初はローカルテンプレートで十分
- APIキーをGitに入れない

### X API

- 料金: https://docs.x.com/x-api/getting-started/pricing
- Developer Portal: https://developer.x.com/
- APIドキュメント: https://docs.x.com/

用途:

- X自動投稿
- 投稿ID取得
- 将来的な指標取得

注意:

- 有料化・従量課金に注意
- 初期はCSVから手動投稿で十分
- 実投稿はテスト後

### Meta / Instagram / Threads

- Meta for Developers: https://developers.facebook.com/
- Instagram Platform: https://developers.facebook.com/docs/instagram-platform/
- Threads API: https://developers.facebook.com/docs/threads/

用途:

- Instagram自動投稿
- Threads自動投稿
- カルーセル投稿

注意:

- Metaログインが必要
- Instagramはプロアカウントが必要
- Instagram自動投稿には公開HTTPS画像URLが必要
- 初期は手動投稿で十分

### LINE

- LINE Developers: https://developers.line.biz/ja/
- Messaging API料金: https://developers.line.biz/ja/docs/messaging-api/pricing/
- LINE公式アカウント: https://www.lycbiz.com/jp/service/line-official-account/

用途:

- 将来のLINE導線
- 比較ページからリスト化
- 再訪問導線

注意:

- 初期は不要
- 友だち数が増えてから検討
- 無料通数と料金プランを確認

## 優先度D: 海外展開

### Amazon海外

- Amazon Associates Global: https://affiliate-program.amazon.com/
- OneLink: https://affiliate-program.amazon.com/help/node/topic/GKHRXG4YEJBTCAFC

用途:

- 英語圏向け物販

注意:

- 日本ASPリンクの単純翻訳は弱い
- 国ごとに商品、在庫、配送、成果条件を確認

### グローバルASP

- Impact: https://impact.com/partners/
- PartnerStack: https://partnerstack.com/
- Awin: https://www.awin.com/
- Adobeアフィリエイト: https://www.adobe.com/jp/affiliates.html
- Adobe Expressアフィリエイト: https://www.adobe.com/jp/express/affiliate
- Surfsharkアフィリエイト: https://surfshark.com/ja/affiliate

用途:

- 海外SaaS
- AIツール
- セキュリティ
- B2Bサービス

注意:

- 英語圏向け媒体が必要
- 実利用・仕様確認が必要
- 成果対象地域を確認

## 法令・表示

### 日本のステルスマーケティング規制

- 消費者庁: https://www.caa.go.jp/policies/policy/representation/fair_labeling/stealth_marketing/

使い方:

- 広告表示ルール確認
- SNS投稿のPR表記確認

### 米国FTC

- FTC Disclosures for Social Media Influencers: https://www.ftc.gov/influencers

使い方:

- 海外展開時の広告表示確認

## 分析

### Google

- Google Analytics: https://analytics.google.com/
- Google Search Console: https://search.google.com/search-console/
- Google Trends: https://trends.google.com/trends/

用途:

- アクセス解析
- 検索流入
- キーワード傾向

### 無料の手動分析

- `data/manual_metrics_template.csv`
- `python3 -m trend_commerce report`

初期はGoogle連携前に手動で十分。

## CEOが次に使うURL

1. 楽天アフィリエイト: https://affiliate.rakuten.co.jp/guides/begin/
2. もしもアフィリエイト: https://af.moshimo.com/
3. A8.net: https://www.a8.net/
4. バリューコマース: https://www.valuecommerce.ne.jp/affiliate/
5. SNSアカウントURL入力: `data/social_accounts_template.csv`
6. 手動投稿30本: `samples/social/30_post_manual_test_plan.md`
