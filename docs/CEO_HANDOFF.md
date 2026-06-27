# CEO向け引継ぎ

## まず見る場所

1. `PROJECT_STATUS.md`
2. `output/reports/ceo_report.html`
3. `output/demo/drafts/`
4. `AIアフィリエイト事業設計.md`

## 無料デモ

```bash
python3 -m trend_commerce demo
```

デモは `var/trend_commerce_demo.db` と `output/demo/` を使い、本番候補DBを汚しません。

## 本番候補のShadow Mode

```bash
python3 -m trend_commerce collect
python3 -m trend_commerce run
python3 -m trend_commerce report
```

## 重要

- `run` だけでは外部公開されません。
- `--allow-paid` がない限りOpenAI APIは呼びません。
- WordPressアダプタは必ず `status=draft` を送ります。
- サンプル商品は実在リンクではなく調査用です。
- 気象庁の災害フィードは意図的に無効です。

