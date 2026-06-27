# 商品別収益分析

## 目的

商品ごとのPV、広告クリック、成約、確定報酬を同じ表で確認し、残す商品と差し替える商品をBOTが判断できるようにする。

## 入力

1. GA4または手入力のクリック指標を`data/affiliate_metrics_template.csv`形式で用意する
2. ASPの成果CSVを既存の`import-conversions`で取り込む

クリック指標の取込:

```bash
python3 -m trend_commerce import-affiliate-metrics --file data/affiliate_metrics_template.csv
```

## 出力

```bash
python3 -m trend_commerce affiliate-report
```

- `output/affiliate_analysis/product_performance.csv`
- `output/affiliate_analysis/product_performance.html`

確定報酬を利益相当額として集計する。広告費や外注費を使い始めた後は、別途コスト列を追加して営業利益へ拡張する。

## BOTの一次判断

- PV100未満: データ収集中
- PV100以上でクリック0: 商品位置とCTAを改善
- CTR 2%未満: タイトルと商品訴求を改善
- 20クリック以上で成約0: 商品価格、販売ページ、読者意図のズレを確認
- EPC 100円超: 維持し、SNSと関連記事へ横展開

データがない商品は自動削除しない。差し替えは商品運用部の販売状況、レビュー品質、在庫確認と合わせて行う。
