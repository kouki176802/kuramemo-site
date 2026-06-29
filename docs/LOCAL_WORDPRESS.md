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

## 比較サイト全体を同期

```bash
python3 -m trend_commerce build-site
python3 -m trend_commerce wordpress-sync --site-dir output/site --status publish
```

- トップはテーマが `output/site/index.html` の本文を表示
- 固定・カテゴリ・比較・入口記事はWordPress固定ページへupsert
- `.html` の内部リンクはWordPressのパーマリンクへ変換
- 商品画像、広告属性、クリック計測を維持
- 外部URLは書き換えない
- ローカル環境は公開状態でも強制 `noindex`

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

会社BOTをまとめて動かす:

```bash
zsh scripts/run_company_bot.command
```

- 1時間ごと: 情報源収集、記事候補処理、CEOレポート
- 24時間ごと: 日本・海外トレンド、商品販売監視、8商品補完、サイト再生成、WordPress同期、SNS A/B学習
- 毎朝7:30以降の最初の巡回: DiscordへX投稿候補を1件送信
- 外部SNSへの実投稿: 明示的に `--live` を付けない限り無効
- APIが停止した場合: タイムアウト後に次の部署へ進み、検証済み商品を維持

## 外部公開するとき

現段階ではルーターのポート開放をしません。外部公開へ移る際は、HTTPS、固定URL、バックアップ、OS更新、WordPress更新、ファイアウォールを先に設定します。公開用サーバーへ移す場合も、記事とテーマはそのまま移行できます。
