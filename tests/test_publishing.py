import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trend_commerce.publishing import WordPressPublisher, discover_generated_pages, markdown_to_wp_html


class PublishingTests(unittest.TestCase):
    def test_markdown_to_wp_html_renders_headings_lists_table_and_disclosure(self):
        content = """# 記事タイトル

> **広告について:** 広告リンクを含みます。

## 選び方

- 用途を見る
- 条件を見る

| 候補 | 確認事項 |
|---|---|
| 標準 | 価格 |
"""
        rendered = markdown_to_wp_html(content)
        self.assertNotIn("<h1>", rendered)
        self.assertIn("<h2>選び方</h2>", rendered)
        self.assertIn("<blockquote>", rendered)
        self.assertIn("<ul>", rendered)
        self.assertIn("<table>", rendered)

    def test_create_draft_from_file_never_publishes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.md"
            path.write_text("# サンプル\n\n本文", encoding="utf-8")
            with patch.dict(os.environ, {
                "WORDPRESS_BASE_URL": "http://127.0.0.1:8080",
                "WORDPRESS_USERNAME": "bot",
                "WORDPRESS_APPLICATION_PASSWORD": "secret",
            }, clear=False):
                publisher = WordPressPublisher()
                with patch.object(publisher, "_request", return_value={"id": 1, "status": "draft"}) as request:
                    result = publisher.create_draft_from_file(path)
            self.assertEqual(result["status"], "draft")
            self.assertEqual(request.call_args.args[1]["status"], "draft")

    def test_discover_generated_pages_reads_title_and_description(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.html"
            path.write_text(
                '<html><head><title>商品比較 | くらメモ</title>'
                '<meta name="description" content="選び方の説明"></head></html>',
                encoding="utf-8",
            )
            pages = discover_generated_pages(Path(temp))
        self.assertEqual(pages, [{"slug": "sample", "title": "商品比較", "description": "選び方の説明"}])

    def test_upsert_page_reuses_draft_slug(self):
        with patch.dict(os.environ, {
            "WORDPRESS_BASE_URL": "http://127.0.0.1:8080",
            "WORDPRESS_USERNAME": "bot",
            "WORDPRESS_APPLICATION_PASSWORD": "secret",
        }, clear=False):
            publisher = WordPressPublisher()
            with patch.object(publisher, "_request", side_effect=[
                [{"id": 3, "slug": "privacy-policy", "status": "draft"}],
                {"id": 3, "slug": "privacy-policy", "status": "publish"},
            ]) as request:
                result = publisher.upsert_page(
                    slug="privacy-policy", title="プライバシーポリシー", excerpt="説明",
                )
        self.assertEqual(result["id"], 3)
        self.assertIn("status=any", request.call_args_list[0].args[0])
        self.assertEqual(request.call_args_list[1].args[0], "/wp-json/wp/v2/pages/3")


if __name__ == "__main__":
    unittest.main()
