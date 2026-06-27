import csv
import tempfile
import unittest
from pathlib import Path

from trend_commerce.catalog import import_offers, match_offers
from trend_commerce.clustering import _choose_category
from trend_commerce.database import initialize
from trend_commerce.settings import Settings


def settings_for(root: Path) -> Settings:
    return Settings(
        company_name="test", timezone="Asia/Tokyo", database_path=root / "db.sqlite",
        output_dir=root / "output", draft_threshold=65, auto_publish_threshold=999,
        max_candidates_per_run=3, max_daily_generation_cost_yen=0,
        categories=["季節・暮らし", "美容・フィットネス", "AI・ガジェット"],
        banned_topics=[], dark_pattern_terms=[], openai_model="gpt-test",
    )


class CatalogClusteringTest(unittest.TestCase):
    def test_classifier_overrides_unrelated_source_hint(self):
        category = _choose_category("生成AIの新機能を発表", "文書整理に対応", "季節・暮らし")
        self.assertEqual(category, "AI・ガジェット")

    def test_category_alone_does_not_match_offer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = settings_for(root)
            initialize(settings.database_path)
            path = root / "offers.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow([
                    "offer_id", "network", "name", "category", "keywords", "problem_tags", "event_tags",
                    "affiliate_url", "landing_url", "reward_type", "reward_value", "allowed_media", "status", "last_verified_at"
                ])
                writer.writerow(["dehumidifier", "x", "除湿機", "季節・暮らし", "梅雨", "湿気", "梅雨", "", "", "percent", 0, "site", "research", "2026-06-24"])
            import_offers(settings, path)
            self.assertEqual(match_offers(settings, "猛暑予報", "気温上昇", "季節・暮らし"), [])
            self.assertEqual(len(match_offers(settings, "梅雨入り", "湿気が増える", "季節・暮らし")), 1)


if __name__ == "__main__":
    unittest.main()

