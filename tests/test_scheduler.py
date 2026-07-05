import importlib.util
import json
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_shadow_scheduler.py"
spec = importlib.util.spec_from_file_location("company_scheduler", MODULE_PATH)
scheduler = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(scheduler)


class SchedulerTest(unittest.TestCase):
    def test_full_cycle_connects_business_departments(self):
        commands = [" ".join(command) for command in scheduler.cycle_commands(True)]
        joined = "\n".join(commands)
        self.assertIn("trend-screen --max-items 12 --approve --build-site", joined)
        self.assertIn("affiliate-program-scan", joined)
        self.assertIn("product-ops --mode daily", joined)
        self.assertIn("product-expand-cache --target 8", joined)
        self.assertIn("social-ab-release", joined)
        self.assertIn("social-learning-report", joined)
        self.assertIn("wordpress-sync", joined)

    def test_light_cycle_does_not_mutate_products_or_wordpress(self):
        commands = [" ".join(command) for command in scheduler.cycle_commands(False)]
        joined = "\n".join(commands)
        self.assertNotIn("product-ops", joined)
        self.assertNotIn("wordpress-sync", joined)
        self.assertIn("trend_commerce run", joined)

    def test_scheduler_has_twelve_discord_slots(self):
        self.assertEqual(12, len(scheduler.DISCORD_DAILY_SLOTS))
        self.assertEqual((7, 0), scheduler.DISCORD_DAILY_SLOTS[0])
        self.assertEqual((23, 30), scheduler.DISCORD_DAILY_SLOTS[-1])

    def test_scheduler_aligns_to_next_discord_slot(self):
        now = datetime(2026, 6, 30, 7, 2, 0)
        last_sent = datetime(2026, 6, 30, 7, 0, 0)
        self.assertEqual(88 * 60, scheduler._seconds_until_next_discord(now, last_sent))

    def test_scheduler_skips_missed_slots_instead_of_bursting(self):
        now = datetime(2026, 6, 30, 12, 15, 0)
        self.assertEqual(datetime(2026, 6, 30, 11, 30), scheduler._latest_due_discord_slot(now))
        self.assertTrue(scheduler._discord_delivery_due(now, datetime(2026, 6, 30, 8, 30)))
        self.assertFalse(scheduler._discord_delivery_due(now, datetime(2026, 6, 30, 11, 30)))

    def test_scheduler_restores_last_full_cycle_after_restart(self):
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "latest.json"
            log.write_text(json.dumps({
                "last_full_cycle_at": "2026-06-30T19:17:16",
            }), encoding="utf-8")
            self.assertEqual(
                scheduler._load_last_full_cycle(log, Path(tmp) / "missing-latest.json"),
                datetime(2026, 6, 30, 19, 17, 16),
            )


if __name__ == "__main__":
    unittest.main()
