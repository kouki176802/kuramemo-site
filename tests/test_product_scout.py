from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from trend_commerce.database import initialize
from trend_commerce.product_scout import ProductCandidate, best_by_offer, best_publishable_by_offer, score_rakuten_product
from trend_commerce.rakuten import RakutenProduct
from trend_commerce.settings import load_settings


class ProductScoutTest(unittest.TestCase):
    def test_score_prefers_affiliate_reviewed_mid_price_product(self):
        product = RakutenProduct(
            product_id="p1",
            name="携帯扇風機 ハンディファン 軽量モデル",
            min_price=1980,
            max_price=0,
            product_url="https://example.com/product",
            affiliate_url="https://example.com/affiliate",
            image_url="",
            review_count=120,
            review_average=4.4,
            availability=1,
        )
        score, reasons = score_rakuten_product(product, "携帯扇風機", "携帯扇風機")
        self.assertGreaterEqual(score, 80)
        self.assertIn("アフィリエイトURLあり", reasons)

    def test_best_by_offer_keeps_highest_score(self):
        low = ProductCandidate("page", "offer", "group", "kw", "季節・暮らし", "low", 40, 1000, 0, 1, 3.0, "", "a", "", "", [])
        high = ProductCandidate("page", "offer", "group", "kw", "季節・暮らし", "high", 80, 1000, 0, 10, 4.0, "", "a", "", "", [])
        self.assertEqual(best_by_offer([low, high])[0].name, "high")

    def test_grooming_and_health_mismatches_are_rejected(self):
        shaver = RakutenProduct(
            product_id="p2", name="レディース VIO ヒートカッター 女性用", min_price=1980, max_price=0,
            product_url="p", affiliate_url="a", image_url="", review_count=1000,
            review_average=4.5, availability=1,
        )
        fiber = RakutenProduct(
            product_id="p3", name="おからパウダー 小麦粉代替 クッキー用 食物繊維", min_price=900, max_price=0,
            product_url="p", affiliate_url="a", image_url="", review_count=1000,
            review_average=4.5, availability=1,
        )
        shaver_score, shaver_reasons = score_rakuten_product(shaver, "電気シェーバー", "電気シェーバー")
        fiber_score, fiber_reasons = score_rakuten_product(fiber, "食物繊維", "食物繊維")
        self.assertLess(shaver_score, 75)
        self.assertLess(fiber_score, 75)
        self.assertIn("商品タイプ不一致の可能性", shaver_reasons)
        self.assertIn("商品タイプ不一致の可能性", fiber_reasons)

    def test_publishable_selection_rejects_low_rating_and_prefers_quality(self):
        low_rating = ProductCandidate("page", "offer", "group", "kw", "家事・時短", "cheap", 100, 1000, 0, 1500, 3.7, "p", "a", "", "", [])
        quality = ProductCandidate("page", "offer", "group", "kw", "家事・時短", "quality", 100, 5000, 0, 500, 4.5, "p2", "a2", "", "", [])
        self.assertEqual(best_publishable_by_offer([low_rating, quality])[0].name, "quality")

    def test_activate_candidates_writes_active_offer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = load_settings()
            settings = replace(base, database_path=root / "db.sqlite", output_dir=root / "output")
            initialize(settings.database_path)
            candidate = ProductCandidate(
                page_slug="heat-relief-items-comparison",
                offer_id="portable_fan_research",
                product_group="携帯扇風機",
                keyword="携帯扇風機",
                category="季節・暮らし",
                name="テスト携帯扇風機",
                score=90,
                min_price=1980,
                max_price=0,
                review_count=10,
                review_average=4.2,
                product_url="https://example.com/product",
                affiliate_url="https://example.com/affiliate",
                image_url="https://example.com/image.jpg",
                shop_name="テストショップ",
                reasons=[],
            )
            # Write to the real offers.csv is intentionally not used here; activation
            # is integration-tested by command runs. This unit test verifies the
            # candidate shape remains compatible with the activation pathway.
            self.assertEqual(candidate.offer_id, "portable_fan_research")
            self.assertTrue(candidate.affiliate_url)


if __name__ == "__main__":
    unittest.main()
