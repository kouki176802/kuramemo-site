# CEO次アクション

作成日: 2026-06-25

## 2026-06-27時点でCEOに必要なこと

無料で進められる設計・商品選定・サイト生成・X/Instagram投稿候補・Discord通知・商品監査・収益分析の受け皿は完成済みです。いま社長判断が必要なのは登録を伴う次の項目だけです。

1. 公開先とHTTPS URLを決める
2. GA4測定IDとSearch Console確認トークンを取得する
3. Instagramをプロアカウント化し、完全自動投稿する場合だけMeta認証を行う
4. Xへ完全自動投稿する場合だけX APIの費用と利用上限を確認する
5. AIサービス等のASP提携が承認されたらリンクを登録する
6. 以前プロンプトへ直接記載したDiscord Webhookは念のため再発行する

上記が未登録でも、毎朝7時30分にX本文とInstagram 7枚画像をDiscordへ受け取り、手動投稿できます。

## 今すぐCEOがやると進むこと

### 1. 媒体名を決める

現在案:

- 選び方メモ

方向性:

- 売り込み感を出さない
- 比較メディアっぽい
- SNS名にも使える
- 後で複数ジャンルへ広げられる

### 2. SNSアカウントURLを記録

`data/social_accounts_template.csv` に既存アカウントURLを入れる。

必要:

- X
- Threads
- Instagram
- TikTokは任意

### 3. SNSプロフィールを反映

プロフィール文は以下に用意済み。

- `docs/MEDIA_PROFILE.md`
- `data/social_accounts_template.csv`

### 4. 手動投稿を始める

まずは以下から3本だけ投稿。

- `samples/social/30_post_manual_test_plan.md`

投稿後、URLと反応を以下へ記録。

- `data/manual_metrics_template.csv`

### 5. サイト公開準備

ドメイン・サーバーはまだ後でよい。

ただし、公開前に必要なページは準備済み。

- `site_content/homepage.md`
- `site_content/about.md`
- `site_content/advertising_policy.md`
- `site_content/editorial_policy.md`
- `site_content/privacy_policy_template.md`
- `site_content/disclaimer.md`

## Codexが次にできること

CEOの登録・ログインなしで進められる作業:

1. 比較ページ6本をさらに厚くする
2. SNS投稿を100本まで増やす
3. Instagramカルーセル文面を増やす
4. WordPress投稿用のMarkdownを整える
5. 商品候補カテゴリをさらに増やす
6. トレンド入口記事を増やす
7. 内部リンクを記事内へ実装する
8. ローカルBOTに比較ページ更新ロジックを追加する

CEOの入力が必要な作業:

1. SNSアカウントURL
2. 正式媒体名
3. ドメイン
4. WordPress情報
5. ASP登録
6. 実アフィリエイトリンク
7. APIキー

## まだ有料化しなくてよいもの

- OpenAI API
- X API
- WordPressサーバー
- 独自ドメイン
- VPS
- メルマガ配信スタンド
- LINE公式アカウント拡張

まずはSNS手動投稿と比較ページ原稿で十分。

## 次の判断基準

### SNSを始める基準

- プロフィール文が入っている
- 固定投稿がある
- 10本分の投稿案がある

### ASP登録する基準

- サイトまたはSNSが公開されている
- 固定ページがある
- 比較ページが5本以上ある
- 投稿実績がある

### WordPressを契約する基準

- 媒体名が決まっている
- 公開したい比較ページが5本以上ある
- SNSから流す準備がある
- 月1,000〜2,000円程度の固定費を許容できる

### API自動投稿へ進む基準

- 手動投稿で反応がある
- 投稿型が決まっている
- 規約と費用を確認済み
- 停止条件が決まっている
