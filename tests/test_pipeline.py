import csv
import tempfile
import unittest
from pathlib import Path

from trend_commerce.catalog import import_offers
from trend_commerce.collectors import add_manual_signal
from trend_commerce.database import connect, initialize
from trend_commerce.pipeline import run_pipeline
from trend_commerce.settings import Settings, ensure_directories


def make_settings(root: Path) -> Settings:
    return Settings(
        company_name="test",
        timezone="Asia/Tokyo",
        database_path=root / "var" / "test.db",
        output_dir=root / "output",
        draft_threshold=0,
        auto_publish_threshold=999,
        max_candidates_per_run=3,
        max_daily_generation_cost_yen=0,
        categories=["季節・暮らし", "美容・フィットネス", "AI・ガジェット"],
        banned_topics=["治療", "死亡"],
        dark_pattern_terms=["絶対買うべき", "残りわずか"],
        openai_model="gpt-test",
    )


class PipelineTest(unittest.TestCase):
    def test_end_to_end_creates_safe_draft_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            ensure_directories(settings)
            initialize(settings.database_path)
            offers = root / "offers.csv"
            with offers.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow([
                    "offer_id", "network", "name", "category", "keywords", "problem_tags", "event_tags",
                    "affiliate_url", "landing_url", "reward_type", "reward_value", "allowed_media", "status", "last_verified_at"
                ])
                writer.writerow([
                    "fan", "research", "携帯扇風機", "季節・暮らし", "猛暑|暑さ", "暑さ対策", "猛暑",
                    "", "", "percent", "0", "site|x", "research", "2026-06-24"
                ])
            import_offers(settings, offers)
            add_manual_signal(settings, "猛暑予報が発表", "https://example.com/heat", "気温上昇の見込み", "季節・暮らし")
            first = run_pipeline(settings)
            second = run_pipeline(settings)
            self.assertEqual(first["drafts"], 1)
            self.assertEqual(second["drafts"], 0)
            drafts = list((settings.output_dir / "drafts").glob("*.md"))
            self.assertEqual(len(drafts), 1)
            article = drafts[0].read_text(encoding="utf-8")
            self.assertIn("広告について", article)
            self.assertIn("買わない場合の代替案", article)
            with connect(settings.database_path) as conn:
                row = conn.execute("SELECT status FROM content_items").fetchone()
                self.assertEqual(row["status"], "approval_required")
                social_count = conn.execute("SELECT COUNT(*) AS c FROM social_posts").fetchone()["c"]
                self.assertEqual(social_count, 4)


if __name__ == "__main__":
    unittest.main()
