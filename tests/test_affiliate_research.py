from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from trend_commerce.affiliate_research import scan_affiliate_programs
from trend_commerce.settings import load_settings


class AffiliateResearchTest(unittest.TestCase):
    def test_scan_writes_a8_review_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = load_settings()
            settings = replace(base, output_dir=Path(tmp))
            result = scan_affiliate_programs(settings)
            self.assertGreaterEqual(result["a8_candidates"], 5)
            content = Path(result["output"]).read_text(encoding="utf-8-sig")
            self.assertIn("提携可否", content)
            self.assertIn("ニュース一致", content)


if __name__ == "__main__":
    unittest.main()
