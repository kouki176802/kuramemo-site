import unittest

from trend_commerce.product_operations import (
    _current_is_weak, _eligible, _rakuten_item_code, _rakuten_shop_code, _selection_index,
)
from trend_commerce.product_scout import ProductCandidate


def candidate(**overrides):
    values = {
        "page_slug": "page", "offer_id": "offer", "product_group": "充電器", "keyword": "充電器",
        "category": "AI・ガジェット", "name": "USB-C充電器", "score": 90,
        "min_price": 3000, "max_price": 0, "review_count": 100, "review_average": 4.4,
        "product_url": "https://item.rakuten.co.jp/shop/item/", "affiliate_url": "https://example.com/affiliate",
        "image_url": "https://example.com/image.jpg", "shop_name": "shop", "reasons": ["商品名一致:充電器"],
    }
    values.update(overrides)
    return ProductCandidate(**values)


class ProductOperationsTest(unittest.TestCase):
    def test_extracts_item_code_from_direct_and_affiliate_urls(self):
        self.assertEqual(_rakuten_item_code("https://item.rakuten.co.jp/shop/item/"), "shop:item")
        wrapped = "https://hb.afl.rakuten.co.jp/hgc/x/?pc=https%3A%2F%2Fitem.rakuten.co.jp%2Fshop%2Fitem%2F"
        self.assertEqual(_rakuten_item_code(wrapped), "shop:item")
        self.assertEqual(_rakuten_shop_code(wrapped), "shop")
        wrapped_with_mobile = wrapped + "&m=http%3A%2F%2Fm.rakuten.co.jp%2Fshop%2Fi%2F10000573%2F"
        self.assertEqual(_rakuten_item_code(wrapped_with_mobile), "shop:10000573")

    def test_candidate_quality_gate_rejects_thin_or_mismatched_items(self):
        self.assertTrue(_eligible(candidate()))
        self.assertFalse(_eligible(candidate(review_count=5)))
        self.assertFalse(_eligible(candidate(review_average=3.5)))
        self.assertFalse(_eligible(candidate(reasons=["商品タイプ不一致の可能性"])))

    def test_selection_index_rewards_reviewed_high_rating_items(self):
        self.assertGreater(_selection_index(candidate(review_count=1000, review_average=4.6)), _selection_index(candidate(review_count=20, review_average=4.0)))

    def test_current_weakness_guard(self):
        self.assertTrue(_current_is_weak({"review_count": "10", "review_average": "4.8"}))
        self.assertTrue(_current_is_weak({"review_count": "100", "review_average": "3.7"}))
        self.assertFalse(_current_is_weak({"review_count": "100", "review_average": "4.2"}))


if __name__ == "__main__":
    unittest.main()
