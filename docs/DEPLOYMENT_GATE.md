# 公開ゲート

## ローカル確認

```bash
python3 -m trend_commerce build-site
python3 -m trend_commerce publish-check
```

公開URLが未設定の間は意図的に失敗する。ローカル版は`noindex,nofollow`のまま保持される。

## 公開ビルド

`.env`へ設定する。

```env
SITE_BASE_URL=https://公開ドメイン
GA4_MEASUREMENT_ID=G-XXXXXXXXXX
GSC_VERIFICATION=確認トークン
```

再生成後に検査する。

```bash
python3 -m trend_commerce build-site
python3 -m trend_commerce publish-check
```

`ready: true`になった出力だけを公開先へ配置する。GA4とSearch Consoleは警告扱いなので、サイトだけ先に公開することはできる。

## GitHub Pagesで計測値を設定する

公開リポジトリの `Settings > Secrets and variables > Actions > Variables` に、次のRepository variableを登録する。

- `GA4_MEASUREMENT_ID`: GA4の測定ID（`G-`から始まる値）
- `GSC_VERIFICATION`: Search ConsoleのHTMLタグに含まれる`content`の値だけ

どちらも公開HTMLへ埋め込まれる検証・計測用の値であり、APIキーやログインパスワードは登録しない。値を追加または変更したら、`Deploy Kuramemo to GitHub Pages`を再実行する。通常ページに加え、専用の占いLPにも同じ設定が反映される。

## 検査内容

- HTTPSの公開URL
- 必須固定ページ6件
- noindexの残存
- localhostの混入
- robots.txtの公開状態
- sitemap.xml
- 未接続商品枠
- GA4とSearch Consoleの設定
