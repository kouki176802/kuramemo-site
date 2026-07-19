from __future__ import annotations

import tempfile
import unittest
import csv
from dataclasses import replace
from pathlib import Path

from trend_commerce.catalog import upsert_offer_csv
from trend_commerce.settings import load_settings
from trend_commerce.static_site import (
    _category_product_signal,
    _category_trend_reason,
    _home_featured_trend,
    _home_trend_cards,
    build_static_site,
    markdown_to_html,
)


class StaticSiteTest(unittest.TestCase):
    def test_home_trends_lead_with_product_and_explain_attention(self):
        row = {
            "score": "88",
            "country_name": "韓国",
            "market_label": "韓国で検索急上昇",
            "page_slug": "trend-cosmetics-comparison",
            "item_name": "テスト リップティント",
            "topic": "韓国SNSで新色リップが話題",
            "news_source": "公式発表",
            "image_url": "https://example.com/lip.jpg",
            "price": "1980",
            "review_count": "450",
            "review_average": "4.6",
        }
        cards = _home_trend_cards([row])
        feature, notes = _home_featured_trend([row])
        self.assertIn("テスト リップティント", cards)
        self.assertIn("話題のきっかけ", cards)
        self.assertIn("なぜ掲載？", cards)
        self.assertIn("ニュース・SNSと海外トレンド", cards)
        self.assertIn("なぜこの商品？", feature)
        self.assertIn("韓国で検索急上昇", feature)
        self.assertIn("注目の根拠", notes)

    def test_japan_trend_does_not_overstate_country_but_overseas_does(self):
        japan = {
            "score": "80", "country_name": "日本", "market_label": "日本のニュースで注目",
            "page_slug": "travel-outdoor-items-comparison", "item_name": "旅行バッグ",
            "topic": "旅行用品が話題", "news_source": "ニュース媒体",
        }
        korea = dict(japan, country_name="韓国", market_label="韓国で検索急上昇", score="81")
        japan_cards = _home_trend_cards([japan])
        korea_cards = _home_trend_cards([korea])
        self.assertIn("ニュースで注目", japan_cards)
        self.assertNotIn("日本のニュースで注目", japan_cards)
        self.assertNotIn("日本で販売中", japan_cards)
        self.assertIn("韓国で検索急上昇", korea_cards)
        self.assertIn("日本で購入できる", korea_cards)

    def test_category_product_signals_distinguish_trend_reviews_and_purpose(self):
        trend = {
            "country_name": "韓国", "market_label": "韓国で検索急上昇",
            "news_source": "公式発表", "topic": "新商品が話題",
        }
        self.assertEqual("今話題", _category_product_signal({}, trend)[1])
        self.assertEqual("口コミ多数", _category_product_signal({"review_count": "800"}, None)[1])
        self.assertEqual("用途一致", _category_product_signal({"review_count": "12"}, None)[1])
        reason = _category_trend_reason(trend)
        self.assertIn("韓国で検索急上昇", reason)
        self.assertIn("日本で購入できる", reason)

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
            self.assertGreaterEqual(result["service_on_page_min_score"], 90)
            index = root / "output" / "site" / "index.html"
            heat = root / "output" / "site" / "heat-relief-items-comparison.html"
            article = root / "output" / "site" / "charger-selection.html"
            beauty = root / "output" / "site" / "category-beauty.html"
            fitness = root / "output" / "site" / "category-fitness.html"
            health = root / "output" / "site" / "category-health.html"
            trend_cosmetics = root / "output" / "site" / "trend-cosmetics-comparison.html"
            services = root / "output" / "site" / "category-services.html"
            mobile_services = root / "output" / "site" / "mobile-carrier-services.html"
            investment_services = root / "output" / "site" / "investment-account-services.html"
            hair_removal = root / "output" / "site" / "hair-removal-services.html"
            internet_line = root / "output" / "site" / "internet-line-services.html"
            streaming = root / "output" / "site" / "streaming-services.html"
            credit_card = root / "output" / "site" / "credit-card-services.html"
            click_report = root / "output" / "site" / "click-report.html"
            not_found = root / "output" / "site" / "404.html"
            self.assertTrue(index.exists())
            index_html = index.read_text(encoding="utf-8")
            self.assertIn("注目の理由をまとめて見る", index_html)
            self.assertIn("この商品を比較する", index_html)
            self.assertTrue(heat.exists())
            self.assertTrue(article.exists())
            self.assertTrue(beauty.exists())
            self.assertTrue(fitness.exists())
            self.assertTrue(health.exists())
            self.assertTrue(trend_cosmetics.exists())
            self.assertTrue(services.exists())
            self.assertTrue(mobile_services.exists())
            self.assertTrue(investment_services.exists())
            self.assertTrue(hair_removal.exists())
            self.assertTrue(internet_line.exists())
            self.assertTrue(streaming.exists())
            self.assertTrue(credit_card.exists())
            self.assertIn("解約条件", hair_removal.read_text(encoding="utf-8"))
            self.assertIn("工事費", internet_line.read_text(encoding="utf-8"))
            self.assertIn("同時視聴", streaming.read_text(encoding="utf-8"))
            self.assertIn("リボ払い", credit_card.read_text(encoding="utf-8"))
            for service_page in (mobile_services, investment_services, hair_removal, internet_line, streaming, credit_card):
                service_html = service_page.read_text(encoding="utf-8")
                self.assertIn("SEARCH INTENT", service_html, service_page.name)
                self.assertIn("このページの比較基準", service_html, service_page.name)
                self.assertIn("比較前に知っておきたい用語", service_html, service_page.name)
                self.assertNotIn("<th>確認先</th>", service_html, service_page.name)
                self.assertNotIn("<th>広告状況</th>", service_html, service_page.name)
            self.assertIn("楽天モバイル公式", mobile_services.read_text(encoding="utf-8"))
            investment_html = investment_services.read_text(encoding="utf-8")
            self.assertNotIn("アフィリエイト状況", investment_html)
            self.assertNotIn("提携先を調査中", investment_html)
            self.assertIn("2026年7月 公式情報で確認できた差", investment_html)
            self.assertIn("service-provider-heading", investment_html)
            self.assertIn("ネット証券おすすめ比較 2026｜NISA・手数料で選ぶ", investment_html)
            self.assertIn("今は契約しない方がよい人", investment_html)
            self.assertIn("category-services.html", index_html)
            self.assertFalse((root / "output" / "site" / "category-beauty-fitness.html").exists())
            self.assertNotIn("公開中のガイド", beauty.read_text(encoding="utf-8"))
            self.assertIn("charging-power-items-comparison.html", article.read_text(encoding="utf-8"))
            self.assertFalse(click_report.exists())
            self.assertTrue(not_found.exists())
            self.assertIn('name="robots" content="noindex,', not_found.read_text(encoding="utf-8"))
            self.assertNotIn("クリック分析", index.read_text(encoding="utf-8"))
            html = heat.read_text(encoding="utf-8")
            self.assertIn("用途別に確認する商品", html)
            self.assertIn("a8-inline-break", html)
            self.assertTrue("商品リンク準備中" in html or "楽天で詳細を確認する" in html)
            if "楽天で詳細を確認する" in html:
                self.assertIn("この商品を載せる理由", html)
            for comparison in (root / "output" / "site").glob("*-comparison.html"):
                comparison_html = comparison.read_text(encoding="utf-8")
                active_cards = comparison_html.count("offer-card offer-card-active")
                reasons = comparison_html.count('class="offer-evidence')
                self.assertEqual(active_cards, reasons, comparison.name)

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
            self.assertIn('<link rel="canonical" href="https://kuramemo.example/">', index)
            self.assertIn('application/ld+json', index)
            self.assertIn('og:title', index)
            self.assertIn('G-ABC123', index)
            self.assertIn('google-site-verification', index)
            self.assertIn('affiliate_click', (site / "click-tracker.js").read_text(encoding="utf-8"))
            self.assertIn('https://kuramemo.example/sitemap.xml', (site / "robots.txt").read_text(encoding="utf-8"))
            self.assertIn('<loc>https://kuramemo.example/</loc>', (site / "sitemap.xml").read_text(encoding="utf-8"))
            self.assertNotIn('https://kuramemo.example/404.html', (site / "sitemap.xml").read_text(encoding="utf-8"))
            fortune = (site / "fortune-consultation-services.html").read_text(encoding="utf-8")
            self.assertIn('FROM SOCIAL', fortune)
            self.assertIn('https://kuramemo.example/fortune-consultation-services.html', fortune)
            self.assertIn('fortune-consultation-assets/styles.css', fortune)
            self.assertIn('G-ABC123', fortune)
            self.assertIn('<meta name="google-site-verification" content="verify-token">', fortune)
            self.assertTrue((site / "fortune-consultation-assets" / "script.js").exists())
            self.assertTrue((site / "fortune-consultation-services" / "index.html").exists())

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
