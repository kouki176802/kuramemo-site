import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_shadow_scheduler.py"
spec = importlib.util.spec_from_file_location("company_scheduler", MODULE_PATH)
scheduler = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(scheduler)


class SchedulerTest(unittest.TestCase):
    def test_full_cycle_connects_business_departments(self):
        commands = [" ".join(command) for command in scheduler.cycle_commands(True)]
        joined = "\n".join(commands)
        self.assertIn("trend-screen --build-site", joined)
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


if __name__ == "__main__":
    unittest.main()
