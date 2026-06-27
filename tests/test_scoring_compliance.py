import tempfile
import unittest
from pathlib import Path

from trend_commerce.compliance import check_article
from trend_commerce.models import ArticleBundle
from trend_commerce.scoring import score_event
from trend_commerce.settings import Settings


def settings_for(root: Path) -> Settings:
    return Settings(
        company_name="test",
        timezone="Asia/Tokyo",
        database_path=root / "test.db",
        output_dir=root / "output",
        draft_threshold=65,
        auto_publish_threshold=999,
        max_candidates_per_run=3,
        max_daily_generation_cost_yen=0,
        categories=["季節・暮らし", "美容・フィットネス", "AI・ガジェット"],
        banned_topics=["治療", "死亡"],
        dark_pattern_terms=["絶対買うべき", "残りわずか"],
        openai_model="gpt-test",
    )


class ScoringComplianceTest(unittest.TestCase):
    def test_high_risk_term_sets_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = settings_for(Path(tmp))
            score = score_event(settings, "病気の治療法", "必ず治療できる", [], 1, "", 3)
            self.assertTrue(score.risk_flags)
            self.assertEqual(score.safety, 0)

    def test_dark_pattern_is_not_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = settings_for(Path(tmp))
            bundle = ArticleBundle(
                title="絶対買うべき商品",
                slug="x",
                meta_description="x",
                lead="x",
                body_markdown="広告について\n買わない場合の代替案\n出典・確認日時",
                cta_blocks=[{"label": "確認", "offer_id": "x"}],
                social_assets={},
                behavioral_principles=[],
                objections=["価格", "必要性", "互換性"],
                non_purchase_option="買わない",
                urgency_source="https://example.com/source",
                evidence_urls=["https://example.com/source"],
            )
            result = check_article(settings, bundle)
            self.assertEqual(result.decision, "revision_required")
            self.assertGreater(result.dark_pattern_score, 10)


if __name__ == "__main__":
    unittest.main()

