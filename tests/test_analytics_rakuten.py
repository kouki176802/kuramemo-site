import tempfile
import unittest
from pathlib import Path

from trend_commerce.analytics import import_conversions
from trend_commerce.database import connect, initialize
from trend_commerce.rakuten import parse_items, parse_products
from trend_commerce.settings import Settings


def settings_for(root: Path) -> Settings:
    return Settings(
        company_name="test", timezone="Asia/Tokyo", database_path=root / "db.sqlite",
        output_dir=root / "output", draft_threshold=65, auto_publish_threshold=999,
        max_candidates_per_run=3, max_daily_generation_cost_yen=0,
        categories=[], banned_topics=[], dark_pattern_terms=[], openai_model="gpt-test",
    )


class AnalyticsRakutenTest(unittest.TestCase):
    def test_conversion_batch_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = settings_for(root)
            initialize(settings.database_path)
            path = root / "sales.csv"
            path.write_text(
                "transaction_id,network,offer_id,occurred_at,status,amount,content_slug\n"
                "tx-1,a8,,2026-06-24T10:00:00+09:00,approved,1500,trend-1\n",
                encoding="utf-8",
            )
            first = import_conversions(settings, path)
            second = import_conversions(settings, path)
            self.assertEqual(first["inserted"], 1)
            self.assertEqual(second["duplicate_batch"], 1)
            with connect(settings.database_path) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) AS c FROM conversions").fetchone()["c"], 1)

    def test_rakuten_parser_tolerates_wrapped_shape(self):
        payload = {
            "Products": [
                {"Product": {"productId": "p1", "productName": "テスト製品", "minPrice": 1000, "maxPrice": 2000}}
            ]
        }
        products = parse_products(payload)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].product_id, "p1")
        self.assertEqual(products[0].min_price, 1000)

    def test_rakuten_item_parser_reads_availability_and_affiliate_url(self):
        payload = {
            "items": [
                {
                    "itemCode": "shop:item",
                    "itemName": "携帯扇風機",
                    "itemPrice": 1980,
                    "itemUrl": "https://example.com/item",
                    "affiliateUrl": "https://example.com/aff",
                    "availability": 1,
                    "postageFlag": 0,
                    "reviewCount": 20,
                    "reviewAverage": 4.2,
                    "shopName": "テスト店",
                }
            ]
        }
        items = parse_items(payload)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].product_id, "shop:item")
        self.assertEqual(items[0].availability, 1)
        self.assertEqual(items[0].affiliate_url, "https://example.com/aff")


if __name__ == "__main__":
    unittest.main()
