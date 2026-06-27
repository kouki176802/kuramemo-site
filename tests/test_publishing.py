import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trend_commerce.publishing import WordPressPublisher, markdown_to_wp_html


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


if __name__ == "__main__":
    unittest.main()
