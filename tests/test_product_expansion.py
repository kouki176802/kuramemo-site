import unittest

from trend_commerce.product_expansion import _eligible
from trend_commerce.product_scout import ProductCandidate


def candidate(name: str, group: str) -> ProductCandidate:
    return ProductCandidate(
        page_slug="page", offer_id="slot", product_group=group, keyword=group,
        category="健康", name=name, score=90, min_price=1000, max_price=1000,
        review_count=100, review_average=4.5, product_url="https://example.com/item",
        affiliate_url="https://example.com/affiliate", image_url="https://example.com/image.jpg",
        shop_name="shop", reasons=[],
    )


class ProductExpansionTest(unittest.TestCase):
    def test_rejects_product_type_mismatch_even_when_score_is_high(self):
        self.assertFalse(_eligible(candidate("ブルーベリー サプリ 3か月分", "ビタミンC")))

    def test_accepts_reviewed_matching_product(self):
        self.assertTrue(_eligible(candidate("ビタミンC サプリ 90日分", "ビタミンC")))


if __name__ == "__main__":
    unittest.main()
