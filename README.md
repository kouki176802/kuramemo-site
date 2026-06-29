# Trend Commerce BOT

流行・ニュースを監視し、購買機会を採点し、商品候補と結び付け、行動心理学を倫理的に使った記事とSNS投稿を運用するローカルMVPです。

無料のローカル表示だけでも動作します。楽天APIを設定した現在の構成では、販売中商品・画像・レビュー・アフィリエイトURLを自動選定できます。SNS投稿BOTは国別トレンドの収集、投稿生成、承認、予約、重複防止、Discord配信履歴まで管理します。

## 自宅PCでWordPressを使う

ローカルWordPress、専用テーマ、REST API下書き投稿を用意しています。Docker Desktop導入後の手順は [docs/LOCAL_WORDPRESS.md](docs/LOCAL_WORDPRESS.md) を参照してください。外部公開はせず、初期状態では `127.0.0.1` 限定・`noindex` です。

生成済み比較サイトをWordPressへ重複なく同期:

```bash
python3 -m trend_commerce build-site
python3 -m trend_commerce wordpress-sync --site-dir output/site --status publish
```

ローカルでは `publish` にしても強制 `noindex` のため外部公開されません。再実行時は同じスラッグを更新し、ページを増殖させません。

## すぐ試す

```bash
python3 -m trend_commerce init
python3 -m trend_commerce seed
python3 -m trend_commerce demo
python3 -m trend_commerce report
python3 -m unittest discover -s tests -v
python3 scripts/run_evals.py
```

日常運転は次の1本です。PCとDocker Desktopが動いている間、1時間ごとに軽量処理、24時間ごとに全社処理を実行します。外部SNSへは自動投稿しません。

```bash
zsh scripts/run_company_bot.command
```

ターミナルを閉じたままバックグラウンド運転する場合:

```bash
zsh scripts/start_company_bot_background.sh
```

停止は `zsh scripts/stop_company_bot_background.sh` です。PC再起動後は開始コマンドをもう一度実行します。朝のDiscord便は7時30分に時刻を合わせます。外部SNSの実投稿は、API認証と明示フラグを設定するまで行いません。

サイト表示:

```bash
python3 -m http.server 8766 --directory output/site
```

ブラウザで `http://127.0.0.1:8766/` を開きます。

生成物:

- `var/trend_commerce.db`: SQLiteデータベース
- `output/drafts/`: 記事Markdown下書き
- `output/social/`: SNS投稿案
- `output/reports/`: CEO向けレポート

## 基本コマンド

```bash
# RSS/Atomを取得（設定済みの有効ソース）
python3 -m trend_commerce collect

# URLを手動投入
python3 -m trend_commerce add-signal \
  --title "猛暑予報が発表" \
  --url "https://example.com/official-release" \
  --summary "広い地域で気温上昇が見込まれる"

# 未処理シグナルを採点し、下書きを作る
python3 -m trend_commerce run

# CEOレポート
python3 -m trend_commerce report

# SNS投稿キューを確認、承認、dry-run
python3 -m trend_commerce social-queue
python3 -m trend_commerce social-approve --all
python3 -m trend_commerce social-dispatch

# 日本・アメリカ・韓国・イギリスの検索急上昇と楽天売れ筋を照合し、X/Instagram候補とサイトを更新
python3 -m trend_commerce trend-screen \
  --country JP --country US --country KR --country GB \
  --max-items 6 --approve --build-site

# ASP売上CSVを重複なしで取り込む
python3 -m trend_commerce import-conversions --file data/conversions_template.csv
```

トレンド表示は根拠別に「日本で検索急上昇」「日本のニュースで注目」「アメリカで検索急上昇」などと明記します。Google Trendsだけを根拠に「SNSでバズ」とは表現しません。

## 安全設計

- 医療、金融、事件、死亡、災害便乗、芸能炎上は自動公開禁止
- 偽の希少性、偽カウントダウン、架空レビューを禁止
- 緊急性の出典がない煽り表現をブロック
- 商品を使っていないのに体験談として書かない
- 記事には広告表示、確認日、買わない選択肢を必須化
- WordPress連携を有効化しても初期値は常に `draft`
- 人物名を扱っても、その人物の使用商品だと推測・断定しない
- ニュース掲載品と楽天の関連売れ筋が同一でない場合は明記する

詳しい運用は [SNS投稿BOT仕様](docs/SOCIAL_BOT.md)、[運用手順](docs/OPERATIONS.md)、[事業設計](AIアフィリエイト事業設計.md) を参照してください。

## 現在の事業方針

このプロジェクトは、トレンド連動型の比較メディアとして運用します。

```text
SNS・ニュース・流行
↓
BOTが話題を拾う
↓
SNS投稿 / トレンド入口記事
↓
比較ページ
↓
個別チェック記事
↓
アフィリエイト
```

まず見る場所:

- [成果物一覧](docs/DELIVERABLES_INDEX.md)
- [CEO次アクション](docs/CEO_NEXT_ACTIONS.md)
- [比較サイト方針](docs/COMPARISON_SITE_STRATEGY.md)
- [サイト構造](docs/SITE_STRUCTURE.md)
- [日次運用ランブック](docs/DAILY_OPERATION_RUNBOOK.md)
