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

## 検査内容

- HTTPSの公開URL
- 必須固定ページ6件
- noindexの残存
- localhostの混入
- robots.txtの公開状態
- sitemap.xml
- 未接続商品枠
- GA4とSearch Consoleの設定
