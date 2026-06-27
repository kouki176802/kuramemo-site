# 完全自動化への移行手順

作成日: 2026-06-25

## 結論

完全自動化は可能。ただし、X/Meta/WordPress/OpenAIなど外部APIの認証と費用が必要。

いきなり完全自動にせず、以下の順で進める。

```text
Level 1: 手動投稿
Level 2: BOTキュー + 手動投稿
Level 3: BOTキュー + dry-run自動処理
Level 4: Xだけ少量API実投稿
Level 5: WordPress/Threads/Instagram/API分析へ拡張
```

現在は Level 2 まで完了。

## X APIの費用感

X APIは公式ドキュメント上、クレジット購入型の従量課金。

確認日: 2026-06-25

公式:

- https://docs.x.com/x-api/getting-started/pricing
- https://developer.x.com/

公式ドキュメントでは、投稿作成はリクエスト単位で課金され、URL付き投稿は通常投稿より高い単価として示されている。価格は変わる可能性があるため、実運用前にDeveloper Consoleで必ず確認する。

## 完全自動化に必要なもの

### 必須

- X Developerアカウント
- X APIクレジット
- X投稿権限付きユーザーアクセストークン
- API利用上限
- 投稿停止条件

### サイト連携まで行う場合

- WordPress
- 独自ドメイン
- WordPressアプリケーションパスワード
- `SITE_BASE_URL`

### AI生成まで行う場合

- OpenAI APIキー
- 月額上限

## 安全装置

実投稿スケジューラは、以下を必須にした。

- 既定はdry-run
- `--live` がない限り外部投稿しない
- `--live` には `--i-understand-paid-api` が必要
- `--live` では `--platform` 指定が必須
- 1回の投稿数は `--limit` で制限

## コマンド

### dry-runを1回だけ実行

```bash
python3 scripts/run_shadow_scheduler.py \
  --once \
  --dispatch \
  --platform x \
  --limit 1
```

### dry-runを1時間ごとに実行

```bash
python3 scripts/run_shadow_scheduler.py \
  --dispatch \
  --platform x \
  --limit 1 \
  --interval-minutes 60
```

### X APIで実投稿

実行前に `X_USER_ACCESS_TOKEN` が必要。

```bash
export X_USER_ACCESS_TOKEN="..."

python3 scripts/run_shadow_scheduler.py \
  --once \
  --dispatch \
  --platform x \
  --limit 1 \
  --live \
  --i-understand-paid-api
```

## 初期の完全自動運用ルール

- Xのみ
- 1日1〜2投稿まで
- URLなし投稿中心
- アフィリエイトリンクなし
- 健康・美容・金融・災害系は自動投稿しない
- 3日ごとに手動確認
- 反応が悪い投稿型は止める

## まだ完全自動にしないもの

- Threads
- Instagram
- アフィリエイトリンク付き投稿
- WordPress公開投稿
- 高単価案件
- 健康・美容の強い訴求

## CEO作業

完全自動化には、CEO側で次が必要。

1. X Developer Consoleを開く
2. APIクレジット購入
3. 投稿権限付きアプリ作成
4. ユーザーアクセストークン取得
5. 月額/使用上限設定
6. トークンを環境変数へ設定

パスワードやトークンはチャットに貼らない。

## Codex側でできる次作業

- `.env` 読み込み対応
- API実投稿前の接続テスト
- 1日投稿数制限
- 投稿後メトリクス取得
- 失敗時通知
- Mac起動時の自動起動設定
