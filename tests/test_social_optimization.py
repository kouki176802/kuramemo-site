import tempfile
import unittest
from pathlib import Path

from trend_commerce.database import initialize, transaction
from trend_commerce.settings import Settings
from trend_commerce.social_optimization import (
    add_funnel_metric, information_gap_hooks, learning_rows, register_experiment, release_b_variants,
    x_post_quality_checks, x_post_quality_score,
)


def settings_for(root: Path) -> Settings:
    return Settings(
        company_name="test", timezone="Asia/Tokyo", database_path=root / "db.sqlite",
        output_dir=root / "output", draft_threshold=0, auto_publish_threshold=999,
        max_candidates_per_run=3, max_daily_generation_cost_yen=0,
        categories=[], banned_topics=[], dark_pattern_terms=[], openai_model="gpt-test",
        site_base_url="",
    )


class SocialOptimizationTest(unittest.TestCase):
    def test_hooks_keep_country_and_answer_promise(self):
        hooks = information_gap_hooks("韓国で検索急上昇", "グラススキン", "現地メディアで紹介が増加")
        self.assertEqual(2, len(hooks))
        self.assertIn("なぜ", hooks[0]["text"])
        self.assertIn("韓国", hooks[1]["text"])
        self.assertNotIn("注目で広がる", hooks[1]["text"])
        self.assertTrue(all(hook["promise"] == "現地メディアで紹介が増加" for hook in hooks))

    def test_x_quality_checks_require_hook_source_axis_and_action(self):
        strong = (
            "韓国で伸びてるグラススキン、なぜ今見られてる？\n\n"
            "SNSで紹介が増えている背景があります。日本で選ぶなら、価格より先に肌質・成分・返品条件を確認。\n\n"
            "比較はプロフィールのくらメモへ"
        )
        checks = x_post_quality_checks(strong)
        self.assertTrue(all(checks.values()))
        self.assertEqual(100, x_post_quality_score(strong))

        weak = "この商品は人気です。おすすめです。"
        self.assertLess(x_post_quality_score(weak), 50)

    def test_learning_waits_for_sample_then_selects_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = settings_for(Path(tmp))
            initialize(settings.database_path)
            with transaction(settings.database_path) as conn:
                conn.execute("INSERT INTO trend_events(canonical_topic,title) VALUES ('x','x')")
                event_id = conn.execute("SELECT id FROM trend_events").fetchone()["id"]
                conn.execute("INSERT INTO content_items(event_id,content_type,title,slug,file_path) VALUES (?,'trend_social','t','s','x')", (event_id,))
                content_id = conn.execute("SELECT id FROM content_items").fetchone()["id"]
                ids = []
                for variant in ("A", "B"):
                    cursor = conn.execute(
                        """INSERT INTO social_posts(content_id,platform,variant_key,post_text,fingerprint,scheduled_at)
                        VALUES (?,'x',?,?,?,CURRENT_TIMESTAMP)""",
                        (content_id, "v" + variant, "投稿" + variant, "fp" + variant),
                    )
                    ids.append(int(cursor.lastrowid))
                    register_experiment(conn, "exp", ids[-1], variant, "reason_question", "答え")
            add_funnel_metric(settings, ids[0], "2026-06-29", 1000, 100, 90, 3600, 5, 500)
            add_funnel_metric(settings, ids[1], "2026-06-29", 1000, 40, 35, 700, 1, 100)
            rows = learning_rows(settings)
            winner = next(row for row in rows if row["variant"] == "A")
            loser = next(row for row in rows if row["variant"] == "B")
            self.assertEqual("勝ちパターン", winner["decision"])
            self.assertEqual("停止候補", loser["decision"])
            self.assertEqual(10.0, winner["ctr"])
            self.assertEqual(5.0, winner["cvr"])

    def test_b_variant_releases_only_after_a_reaches_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = settings_for(Path(tmp))
            initialize(settings.database_path)
            with transaction(settings.database_path) as conn:
                conn.execute("INSERT INTO trend_events(canonical_topic,title) VALUES ('x','x')")
                event_id = conn.execute("SELECT id FROM trend_events").fetchone()["id"]
                conn.execute("INSERT INTO content_items(event_id,content_type,title,slug,file_path) VALUES (?,'trend_social','t','s','x')", (event_id,))
                content_id = conn.execute("SELECT id FROM content_items").fetchone()["id"]
                post_ids = []
                for variant, status in (("A", "published"), ("B", "experiment_hold")):
                    cursor = conn.execute(
                        """INSERT INTO social_posts(content_id,platform,variant_key,post_text,fingerprint,scheduled_at,status)
                        VALUES (?,'x',?,?,?,CURRENT_TIMESTAMP,?)""",
                        (content_id, "v" + variant, "投稿" + variant, "fp" + variant, status),
                    )
                    post_ids.append(int(cursor.lastrowid))
                    register_experiment(conn, "exp", post_ids[-1], variant, "reason_question", "答え")
            add_funnel_metric(settings, post_ids[0], "2026-06-29", 499)
            self.assertEqual(0, release_b_variants(settings))
            add_funnel_metric(settings, post_ids[0], "2026-06-30", 1)
            self.assertEqual(1, release_b_variants(settings))


if __name__ == "__main__":
    unittest.main()
