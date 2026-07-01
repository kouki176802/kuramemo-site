from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from trend_commerce.publish_check import check_publish_ready
from trend_commerce.settings import load_settings
from trend_commerce.static_site import build_static_site


class PublishCheckTest(unittest.TestCase):
    def test_local_build_is_not_publish_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = load_settings()
            settings = replace(
                base,
                output_dir=Path(tmp) / "output",
                database_path=Path(tmp) / "db.sqlite3",
                site_base_url="",
            )
            build_static_site(settings)
            result = check_publish_ready(settings, settings.output_dir / "site")
            self.assertFalse(result["ready"])
            self.assertTrue(any("SITE_BASE_URL" in item for item in result["errors"]))

    def test_public_build_passes_with_optional_analytics_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = load_settings()
            settings = replace(
                base,
                output_dir=Path(tmp) / "output",
                database_path=Path(tmp) / "db.sqlite3",
                site_base_url="https://kuramemo.example",
            )
            build_static_site(settings)
            result = check_publish_ready(settings, settings.output_dir / "site")
            self.assertTrue(result["ready"])
            self.assertIn("GA4測定IDが未設定", result["warnings"])
            self.assertEqual("kuramemo.example\n", (settings.output_dir / "site" / "CNAME").read_text())
