from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent


class DockerOperationTest(unittest.TestCase):
    def test_company_bot_is_restartable_and_safe_by_default(self) -> None:
        compose = (ROOT / "docker-compose.wordpress.yml").read_text(encoding="utf-8")
        self.assertIn("company-bot:", compose)
        self.assertIn("restart: unless-stopped", compose)
        self.assertIn("scripts/run_shadow_scheduler.py", compose)
        self.assertIn("WORDPRESS_BASE_URL: http://wordpress", compose)
        self.assertIn("scripts/company_bot_healthcheck.py", compose)
        self.assertNotIn("--live", compose)

    def test_setup_starts_company_bot(self) -> None:
        setup = (ROOT / "scripts" / "setup_local_wordpress.sh").read_text(encoding="utf-8")
        self.assertIn("up -d company-bot", setup)


if __name__ == "__main__":
    unittest.main()
