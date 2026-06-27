# ローカルクリック分析

## 目的

GA4やASP連携を入れる前に、商品リンクがクリックされるかを無料で確認する。

現在の静的サイトには `click-tracker.js` を同梱している。
商品リンクをクリックすると、同じブラウザの `localStorage` にクリックログを保存する。

## 確認方法

クリック分析画面は運営者専用情報のため、公開サイトの生成対象・ナビ・フッターから除外する。
現在はブラウザ内の `localStorage` にログだけを保存し、公開ページから閲覧できない状態にする。

## 記録される項目

- clicked_at
- page_slug
- offer_id
- network
- product_group
- link_text
- href

## 使い方

1. 比較ページを開く
2. 商品リンクをクリックする
3. 開発環境でログをCSV化する
4. 商品別クリック数を見る
5. `outputs/affiliate_analysis/affiliate_analysis_dashboard.xlsx` の Daily Input に転記する

## 注意

- このログは同じブラウザ内にだけ保存される
- 外部送信はしない
- サーバー集計ではない
- クリック分析画面は公開フォルダへ出力しない
- 本番公開後は GA4 イベント計測へ置き換える

## 次の拡張

- GA4 `affiliate_click` イベント送信
- Search Console のページ別検索流入取り込み
- 楽天/A8/もしも成果CSV取り込み
- クリック率が低い商品カードの自動改善提案
