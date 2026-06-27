import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from trend_commerce.affiliate_performance import import_affiliate_metrics, write_affiliate_performance_report
from trend_commerce.catalog import import_offers
from trend_commerce.database import initialize
from trend_commerce.settings import load_settings


class AffiliatePerformanceTest(unittest.TestCase):
    def test_imports_metrics_and_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = load_settings()
            settings = replace(base, database_path=root / "db.sqlite", output_dir=root / "output")
            initialize(settings.database_path)
            import_offers(settings)
            path = root / "metrics.csv"
            path.write_text(
                "measured_date,page_slug,offer_id,page_views,affiliate_clicks\n"
                "2026-06-27,heat-relief-items-comparison,portable_fan_research,100,8\n",
                encoding="utf-8",
            )
            result = import_affiliate_metrics(settings, path)
            self.assertEqual(result["upserted"], 1)
            report = write_affiliate_performance_report(settings)
            self.assertTrue(Path(report["csv"]).exists())
            self.assertTrue(Path(report["html"]).exists())
            self.assertIn("portable_fan_research", Path(report["csv"]).read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
