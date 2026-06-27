# 自宅PC版WordPress

## 構成

- WordPress: `http://127.0.0.1:8080`
- MariaDB: Docker内部だけで接続
- くらメモテーマ: `wordpress/theme/kuramemo`
- BOT投稿: WordPress REST API、常に下書き
- 検索エンジン: ローカル運用中は強制 `noindex`

ポートは `127.0.0.1` にだけ公開します。同じWi-Fiの別端末やインターネットからはアクセスできません。

## 初回だけ行うこと

1. Docker Desktopをインストールして起動する
2. `config/wordpress.env.example` を `.env.wordpress` にコピーする
3. `.env.wordpress` の3つのパスワードとメールアドレスを変更する
4. `zsh scripts/setup_local_wordpress.sh` を実行する
5. 次のコマンドで投稿BOT専用Application Passwordを作成し、Git管理外の `.env` へ保存する

```bash
python3 scripts/configure_wordpress_bot.py
```

手動で設定する場合は、管理画面の「ユーザー → プロフィール → アプリケーションパスワード」で投稿BOT用パスワードを作り、`.env` に次を設定します。

```dotenv
WORDPRESS_BASE_URL=http://127.0.0.1:8080
WORDPRESS_USERNAME=kuramemo_owner
WORDPRESS_APPLICATION_PASSWORD=発行された値
```

## 接続と下書き投稿

```bash
python3 -m trend_commerce wordpress-check
python3 -m trend_commerce wordpress-draft --file output/drafts/記事.md
```

投稿先は必ず `draft` です。WordPress管理画面で事実・広告表記・商品リンクを確認して公開します。

## 日常操作

起動:

```bash
docker compose --env-file .env.wordpress -f docker-compose.wordpress.yml up -d
```

停止:

```bash
zsh scripts/stop_local_wordpress.sh
```

データはDockerボリュームに残ります。PCを切ればサイトとBOTも止まります。

## 外部公開するとき

現段階ではルーターのポート開放をしません。外部公開へ移る際は、HTTPS、固定URL、バックアップ、OS更新、WordPress更新、ファイアウォールを先に設定します。公開用サーバーへ移す場合も、記事とテーマはそのまま移行できます。
