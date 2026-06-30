import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.company_bot_healthcheck import check_health


class CompanyBotHealthcheckTest(unittest.TestCase):
    def test_recent_success_is_healthy(self) -> None:
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "run.json"
            log.write_text(json.dumps({"results": [
                {"command": "-m trend_commerce run", "returncode": 0},
                {"command": "-m trend_commerce wordpress-sync --site-dir output/site --status publish", "returncode": 0},
            ]}), encoding="utf-8")
            healthy, _ = check_health(log, 60, now=log.stat().st_mtime + 30)
            self.assertTrue(healthy)

    def test_stale_result_is_unhealthy(self) -> None:
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "run.json"
            log.write_text('{"results": []}', encoding="utf-8")
            healthy, message = check_health(log, 60, now=log.stat().st_mtime + 61)
            self.assertFalse(healthy)
            self.assertIn("stale", message)

    def test_wordpress_failure_is_unhealthy(self) -> None:
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "run.json"
            log.write_text(json.dumps({"full_cycle": True, "results": [
                {"command": "-m trend_commerce run", "returncode": 0},
                {
                    "command": "-m trend_commerce wordpress-sync --site-dir output/site --status publish",
                    "returncode": 1,
                },
            ]}), encoding="utf-8")
            healthy, message = check_health(log, 60, now=log.stat().st_mtime)
            self.assertFalse(healthy)
            self.assertIn("wordpress-sync", message)

    def test_missing_generation_task_is_unhealthy(self) -> None:
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "run.json"
            log.write_text('{"full_cycle": false, "results": []}', encoding="utf-8")
            healthy, message = check_health(log, 60, now=log.stat().st_mtime)
            self.assertFalse(healthy)
            self.assertIn("missing", message)


if __name__ == "__main__":
    unittest.main()
