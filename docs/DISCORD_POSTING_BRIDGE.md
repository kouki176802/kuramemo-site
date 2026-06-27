# Discord投稿ブリッジ

作成日: 2026-06-25

## 目的

X APIを使わず、BOTが生成した投稿候補をDiscordへ自動通知する。

Discordには、Xへコピペできる投稿文、X投稿画面URL、投稿後の記録コマンドを送る。Xへの実投稿は手動なので、X API料金はかからない。

## 仕組み

```text
BOT readyキュー
↓
Discord Webhook
↓
Discordチャンネルに投稿候補が届く
↓
X投稿画面を開いてコピペ
↓
投稿URLをDBへ記録
```

## Discord側で必要なもの

- Discordサーバー
- 通知用チャンネル
- Webhook URL

WebhookはDiscord公式ドキュメント上、Botユーザーなしでチャンネルへ投稿できる仕組み。

公式: https://docs.discord.com/developers/resources/webhook

## Webhook URLの作り方

1. Discordで対象サーバーを開く
2. 通知したいチャンネルの設定を開く
3. 連携サービス / Webhookを開く
4. 新しいWebhookを作成
5. Webhook URLをコピー

Webhook URLはパスワードのように扱う。チャットに貼らない。

## プレビュー

Discordへ送らず、内容だけ確認する。

```bash
python3 -m trend_commerce social-discord \
  --platform x \
  --limit 1
```

## Discordへ送信

```bash
export DISCORD_WEBHOOK_URL="..."

python3 -m trend_commerce social-discord \
  --platform x \
  --limit 1 \
  --send
```

## Discordに届く内容

- 投稿候補ID
- 投稿先プラットフォーム
- X投稿画面URL
- 本文入り投稿URL
- コピペ用投稿文
- 投稿後にDBへ記録するコマンド

例:

```text
📝 SNS投稿候補 #2 / x
投稿画面: https://x.com/compose/post
本文入り投稿URL: https://twitter.com/intent/tweet?text=...

コピペ用投稿文
...

投稿後に記録
python3 -m trend_commerce social-mark-published --id 2 --permalink 投稿URL
```

## 費用

- Discord Webhook: 通常無料
- X API: 使わないので0円
- OpenAI API: 使わなければ0円

## 注意

- Discord Webhook URLは公開しない
- Discordへ送るだけではXには投稿されない
- 投稿後は必ず `social-mark-published` でDBに反映する
- 連投しすぎない
- アフィリエイトリンク付き投稿はまだ送らない
