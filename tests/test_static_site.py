from __future__ import annotations

import tempfile
import unittest
import csv
from dataclasses import replace
from pathlib import Path

from trend_commerce.catalog import upsert_offer_csv
from trend_commerce.settings import load_settings
from trend_commerce.static_site import build_static_site, markdown_to_html


class StaticSiteTest(unittest.TestCase):
    def test_markdown_tables_and_lists_render(self):
        html = markdown_to_html("# 見出し\n\n- A\n- B\n\n| 商品 | 注意 |\n|---|---|\n| 扇風機 | 音 |\n")
        self.assertIn("<h1>見出し</h1>", html)
        self.assertIn("<li>A</li>", html)
        self.assertIn("<table>", html)
        self.assertIn("<th>商品</th>", html)

    def test_build_static_site_outputs_comparison_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = load_settings()
            settings = replace(base, database_path=root / "site.db", output_dir=root / "output")
            result = build_static_site(settings)
            self.assertGreaterEqual(result["pages"], 6)
            index = root / "output" / "site" / "index.html"
            heat = root / "output" / "site" / "heat-relief-items-comparison.html"
            article = root / "output" / "site" / "charger-selection.html"
            beauty = root / "output" / "site" / "category-beauty.html"
            fitness = root / "output" / "site" / "category-fitness.html"
            health = root / "output" / "site" / "category-health.html"
            trend_cosmetics = root / "output" / "site" / "trend-cosmetics-comparison.html"
            click_report = root / "output" / "site" / "click-report.html"
            self.assertTrue(index.exists())
            self.assertTrue(heat.exists())
            self.assertTrue(article.exists())
            self.assertTrue(beauty.exists())
            self.assertTrue(fitness.exists())
            self.assertTrue(health.exists())
            self.assertTrue(trend_cosmetics.exists())
            self.assertFalse((root / "output" / "site" / "category-beauty-fitness.html").exists())
            self.assertIn("charging-power-items-comparison.html", article.read_text(encoding="utf-8"))
            self.assertFalse(click_report.exists())
            self.assertNotIn("クリック分析", index.read_text(encoding="utf-8"))
            html = heat.read_text(encoding="utf-8")
            self.assertIn("用途別に確認する商品", html)
            self.assertTrue("商品リンク準備中" in html or "楽天で詳細を確認する" in html)

    def test_public_build_emits_canonical_sitemap_and_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = load_settings()
            settings = replace(
                base,
                database_path=root / "site.db",
                output_dir=root / "output",
                site_base_url="https://kuramemo.example",
                ga4_measurement_id="G-ABC123",
                gsc_verification="verify-token",
            )
            build_static_site(settings)
            site = root / "output" / "site"
            index = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn('<link rel="canonical" href="https://kuramemo.example/index.html">', index)
            self.assertIn('application/ld+json', index)
            self.assertIn('og:title', index)
            self.assertIn('G-ABC123', index)
            self.assertIn('google-site-verification', index)
            self.assertIn('affiliate_click', (site / "click-tracker.js").read_text(encoding="utf-8"))
            self.assertIn('https://kuramemo.example/sitemap.xml', (site / "robots.txt").read_text(encoding="utf-8"))
            self.assertIn('https://kuramemo.example/index.html', (site / "sitemap.xml").read_text(encoding="utf-8"))

    def test_upsert_offer_csv_replaces_existing_offer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "offers.csv"
            values = {
                "offer_id": "test_offer",
                "network": "rakuten",
                "name": "テスト商品",
                "category": "季節・暮らし",
                "keywords": "暑さ",
                "problem_tags": "暑さ対策",
                "event_tags": "夏",
                "affiliate_url": "https://example.com/a",
                "landing_url": "https://example.com/p",
                "reward_type": "percent",
                "reward_value": "2",
                "allowed_media": "site",
                "status": "active",
                "last_verified_at": "2026-06-25",
            }
            upsert_offer_csv(values, path)
            values["name"] = "更新商品"
            upsert_offer_csv(values, path)
            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["name"], "更新商品")


if __name__ == "__main__":
    unittest.main()
