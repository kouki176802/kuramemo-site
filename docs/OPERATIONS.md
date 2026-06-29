# 運用手順

## 現在の運転モード

`Shadow Mode / Level 1` です。BOTは収集・採点・商品照合・記事生成・SNS投稿キュー運用まで行います。SNSはdry-runで、外部公開はしません。

## AI会社の日次運転

```bash
zsh scripts/run_company_bot.command
```

この1本で、国内・海外トレンド収集、商品販売監視、比較ページ再生成、ローカルWordPress同期、SNS A/B案生成、勝ちパターン分析、CEOレポートを接続します。外部SNS投稿は既定で無効です。

1回だけ全処理を確認する場合:

```bash
python3 scripts/run_shadow_scheduler.py --once
```

### 各部署の実装対応

| 会社部署 | 実装モジュール | 出力 |
|---|---|---|
| トレンド情報部 | `collectors.py`, `clustering.py`, `scoring.py` | Opportunity Card相当 |
| 商品・収益部 | `catalog.py`, `product_operations.py`, `product_expansion.py` | 商品候補・販売監視・8商品補完 |
| 編集・行動設計部 | `generation.py` | 記事・SNS下書き |
| 品質・コンプライアンス部 | `compliance.py` | 公開判定 |
| 配信運用部 | `publishing.py`, `social.py` | WordPress下書き、SNSキュー・投稿 |
| データ分析部 | `reporting.py`, `social_optimization.py` | CEOレポート・CTR/滞在/CVR・A/B学習 |
| AI経営執行室 | `pipeline.py`, `cli.py` | ジョブ統括・監査ログ |

## CEOレビュー

1. `output/reports/ceo_report.html` を確認
2. `output/drafts/` の記事を確認
3. 記事IDを `status` で取得
4. 判断を記録

```bash
python3 -m trend_commerce status
python3 -m trend_commerce review --content-id 1 --decision approved --notes "出典確認済み"
```

承認は公開を意味しません。WordPress接続後も、別の公開操作を追加するまで下書きのままです。

## 実在情報源の登録

`config/sources.json` に、利用規約を確認した公式RSS/Atomだけを追加します。

```json
{
  "name": "提供元名",
  "url": "https://example.com/feed.xml",
  "kind": "rss",
  "category": "AI・ガジェット",
  "trust_level": 5,
  "active": true
}
```

ニュース本文、ログインページ、SNS画面、ASP管理画面はスクレイピングしません。

## 商品候補の登録

`data/offers.csv` を編集後、再度 `seed` します。アフィリエイトURLはASP規約と媒体許可を確認してから入力してください。

`status` の意味:

- `research`: 調査用。記事候補には出るが公開リンクにはしない
- `active`: 提携・媒体許可・リンク確認済み
- `paused`: 一時停止
- `ended`: 終了

楽天APIで確認済みの掲載枠は `active` とし、販売中・画像・レビュー・アフィリエイトURLを保存します。API障害時は検証済みキャッシュだけを再利用し、未確認商品を数合わせで公開しません。

## OpenAI APIを後から有効化

1. `.env.example` を参考に環境変数を設定
2. 費用上限をOpenAI側でも設定
3. まず1件だけテスト
4. `--allow-paid` を明示した実行でのみ利用

```bash
export OPENAI_API_KEY="..."
export OPENAI_MODEL="gpt-5.5"
python3 -m trend_commerce run --allow-paid
```

キーがあっても `--allow-paid` を付けない限り課金APIは呼びません。

## WordPressを後から接続

環境変数を設定し、`WordPressPublisher.create_draft()` を呼びます。コードは `status=draft` を固定しており、自動公開しません。

## 緊急停止

- スケジューラを停止
- `config/sources.json` の `active` を `false`
- WordPress連携の環境変数を削除
- 問題記事をWordPressで下書きへ戻す
- `bot_runs` と `compliance_reports` を確認

## 有料化前に未実施の項目

- 独自ドメイン・サーバー契約
- WordPress実サイト接続
- OpenAI API実リクエスト
- 楽天API認証
- Amazon Creators API認証
- ASP提携と実リンク
- X/Threads/Instagram実アカウントでの投稿API疎通
- GA4/Search Console認証
