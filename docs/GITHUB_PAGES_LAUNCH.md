# kuramemo-mk.com 公開手順

サイト生成とGitHub Pagesへのデプロイは `.github/workflows/deploy-pages.yml` で自動化済み。

## ドメイン購入後に行う操作

1. 公開用GitHubリポジトリへこのプロジェクトをpushする
2. GitHubの `Settings > Pages > Build and deployment` で `GitHub Actions` を選ぶ
3. お名前.comのDNSへGitHub Pages用レコードを設定する
4. GitHub PagesのCustom domainへ `kuramemo-mk.com` を入力する
5. DNS Check成功後に `Enforce HTTPS` を有効にする

## DNS

ルートドメイン `kuramemo-mk.com` にはGitHub公式が案内するGitHub Pages用Aレコードを設定する。`www` は公開に使うGitHubユーザーまたは組織の `<account>.github.io` へCNAMEを設定する。

GitHub側のリポジトリが確定してから、表示された値をお名前.comへ入力する。既存の不要なA・AAAA・CNAMEがある場合は競合させない。

## 自動処理

mainブランチへのpushで、テスト、静的サイト生成、公開前検査、CNAME・robots.txt・sitemap.xml生成、GitHub Pagesへのデプロイを行う。

## 公開直後の確認

- `https://kuramemo-mk.com/` が開く
- `https://kuramemo-mk.com/404.html` が開く
- HTTPSへ自動転送される
- `https://kuramemo-mk.com/sitemap.xml` が開く
- 商品リンク、サービス公式リンク、スマホ表示に異常がない

