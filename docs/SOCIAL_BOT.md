# SNS投稿BOT運用仕様

## 結論

投稿BOTは記事の付属機能ではなく、事業の配信中枢です。記事生成後、X・Threads・Instagram用の投稿をキューへ登録し、承認、予約、投稿、履歴、効果測定を一つのSQLiteで管理します。

```text
トレンド検知 → 記事下書き → SNS案生成 → 重複検査 → 投稿キュー
                                              ↓
CEO承認 → 予約時刻到来 → 各SNS API → 投稿ID・成否履歴 → クリック分析
```

初期状態は安全な `dry-run` です。`--live` を明示しない限り外部へ投稿しません。

## 現在できること

- 1記事からX複数案、Threads案、Instagramカルーセル案を登録
- 本文とリンクの指紋による重複登録防止
- 媒体ごとの投稿間隔を考慮した予約
- X投稿は標準280字枠を前提に、URLは23字相当、日本語は重めに見積もって自動調整
- 広告表示の自動付与
- CEO承認・却下
- 予約時刻変更
- dry-run
- X、Threads、InstagramのネイティブAPI接続アダプタ
- 成功ID、失敗理由、試行回数の保存
- 失敗投稿の手動再試行
- CSV書き出しによる無料の手動投稿運用
- 表示、反応、リンククリックの記録とCEOレポート反映

## 日次コマンド

```bash
# 1. 新規記事とSNS案を生成
python3 -m trend_commerce collect
python3 -m trend_commerce run

# 2. キュー確認と承認
python3 -m trend_commerce social-queue
python3 -m trend_commerce social-approve --all

# 3. 外部送信なしで投稿対象を確認
python3 -m trend_commerce social-dispatch

# 4. 認証後のみ実投稿
python3 -m trend_commerce social-dispatch --live --limit 3
```

予約変更、却下、再試行:

```bash
python3 -m trend_commerce social-reschedule --id 1 --scheduled-at 2026-06-25T09:00:00+09:00
python3 -m trend_commerce social-reject --id 2 --reason "表現を修正する"
python3 -m trend_commerce social-retry --id 3
```

API契約前は承認済みキューをCSVに出し、各SNSへ手動投稿できます。

```bash
python3 -m trend_commerce social-export --file output/social/post_queue.csv
```

手動テスト投稿CSVをBOTキューへ取り込むこともできます。

```bash
python3 -m trend_commerce social-import \
  --file samples/social/x_bot_test_posts.csv \
  --platform x \
  --approve
```

手動投稿後は、投稿URLをDBへ反映します。

```bash
python3 -m trend_commerce social-mark-published \
  --id 2 \
  --permalink https://x.com/m0506k/status/POST_ID
```

## 本番接続に必要な環境変数

```bash
export SITE_BASE_URL="https://example.com"

export X_USER_ACCESS_TOKEN="..."

export THREADS_USER_ID="..."
export THREADS_ACCESS_TOKEN="..."

export INSTAGRAM_USER_ID="..."
export INSTAGRAM_ACCESS_TOKEN="..."
export META_GRAPH_VERSION="v24.0"
```

Xはアプリ単体トークンではなく、投稿権限を持つユーザーアクセストークンが必要です。X API利用料は契約・使用量に依存するため、本番前に管理画面で上限を設定します。

Threadsはテキスト投稿を作成後に公開する2段階方式です。Instagramはプロアカウントと公開HTTPS画像URLが必要で、画像コンテナ作成後にカルーセルを公開します。

Instagram画像URLの登録:

```bash
# Codex付属Pythonで7枚のPNGを生成
/Users/matsumotokouki/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m trend_commerce social-render --id 4

# 生成PNGを公開画像置き場へアップロードした後にURLを登録
python3 -m trend_commerce social-set-media --id 4 \
  --url https://cdn.example.com/slide-1.png \
  --url https://cdn.example.com/slide-2.png
python3 -m trend_commerce social-approve --id 4
```

画像生成自体は無料でローカル実行できます。Instagram APIはローカルファイルを直接読めないため、本番自動投稿には画像を公開HTTPS URLへ置く工程が必要です。

## 自動運転

Shadow Modeでは外部投稿せず、期限到来キューだけを確認します。

```bash
python3 scripts/run_shadow_scheduler.py --interval 3600 --dispatch
```

認証、実サイトURL、テスト用アカウントでの確認が済んだ後に限り、`--live` を追加します。

```bash
python3 scripts/run_shadow_scheduler.py --interval 3600 --dispatch --live
```

## 効果測定

API Insights連携前は管理画面の数値を手動登録できます。

```bash
python3 -m trend_commerce social-metric \
  --post-id 1 --measured-at 2026-06-25 \
  --impressions 1000 --likes 25 --link-clicks 18
python3 -m trend_commerce report
```

## 安全停止条件

- 記事URLが仮値のままなら実投稿を停止
- 未承認投稿は送信対象外
- Instagram画像がない場合は送信対象外
- API失敗時は `failed` として理由を記録し、自動連打しない
- 事件、災害、医療、金融など禁止テーマは上流のコンプライアンス検査でキュー登録しない

本番移行時は、最初に各媒体1投稿だけをテストアカウントへ送り、表示、広告表記、リンク先、削除手順を確認します。
