# 技術SEO運用

## 実装済み

- ページ別titleとmeta description
- OGPとXカード
- WebPageまたはArticleのJSON-LD
- canonical URL
- sitemap.xml
- robots.txt
- 比較ページ間の関連リンク
- 公開URL未設定時のnoindex

## 公開前に必要な設定

`.env`へ公開URLを設定して再ビルドする。

```text
SITE_BASE_URL=https://公開ドメイン
```

未設定時は誤公開を防ぐため、生成ページが`noindex,nofollow`、robots.txtが`Disallow: /`になる。

## 公開後の確認

1. sitemap.xmlをSearch Consoleへ送信
2. robots.txtのSitemap URLを確認
3. canonicalが公開ドメインになっているか確認
4. OGPプレビューを確認
5. 比較ページのインデックス登録を確認

