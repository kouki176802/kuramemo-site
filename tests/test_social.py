import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from trend_commerce.database import connect, initialize, transaction
from trend_commerce.settings import Settings
from trend_commerce.social import (
    approve_posts, discord_ready_messages, dispatch, enqueue_social_assets, export_queue, list_queue,
    import_manual_social_posts, mark_post_published, reject_post, reschedule_post, retry_post, set_media_urls,
    X_DAILY_SLOTS_JST, _fit_text, _next_schedule, _x_schedule_has_link, _x_weighted_len,
)


def settings_for(root: Path) -> Settings:
    return Settings(
        company_name="test", timezone="Asia/Tokyo", database_path=root / "db.sqlite",
        output_dir=root / "output", draft_threshold=0, auto_publish_threshold=999,
        max_candidates_per_run=3, max_daily_generation_cost_yen=0,
        categories=[], banned_topics=[], dark_pattern_terms=[], openai_model="gpt-test",
        site_base_url="",
    )


def seed_content(settings: Settings) -> int:
    with transaction(settings.database_path) as conn:
        conn.execute("INSERT INTO trend_events(canonical_topic,title) VALUES ('x','x')")
        event_id = conn.execute("SELECT id FROM trend_events").fetchone()["id"]
        cursor = conn.execute(
            "INSERT INTO content_items(event_id,content_type,title,slug,file_path) VALUES (?,'article','記事','article-1','x.md')",
            (event_id,),
        )
        return int(cursor.lastrowid)


class SocialTest(unittest.TestCase):
    def test_queue_deduplicates_and_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = settings_for(root)
            initialize(settings.database_path)
            content_id = seed_content(settings)
            assets = {"x": ["投稿A", "投稿B"], "threads": ["会話投稿"], "instagram": ["1枚目", "2枚目"]}
            with transaction(settings.database_path) as conn:
                first = enqueue_social_assets(conn, settings, content_id, "article-1", assets)
                second = enqueue_social_assets(conn, settings, content_id, "article-1", assets)
            self.assertEqual(first, 4)
            self.assertEqual(second, 0)
            self.assertEqual(len(list_queue(settings)), 4)
            self.assertEqual(approve_posts(settings, [], approve_all=True), 3)
            path = root / "queue.csv"
            self.assertEqual(export_queue(settings, path), 3)
            self.assertTrue(path.exists())

    def test_x_post_is_trimmed_with_japanese_weighted_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = settings_for(root)
            initialize(settings.database_path)
            content_id = seed_content(settings)
            long_text = "急速充電器はワット数だけで選ぶと失敗しやすいです。" * 20
            with transaction(settings.database_path) as conn:
                enqueue_social_assets(conn, settings, content_id, "article-1", {"x": [long_text], "threads": [], "instagram": []})
            post = next(row for row in list_queue(settings) if row["platform"] == "x")
            self.assertLessEqual(_x_weighted_len(post["post_text"]), 280)

    def test_instagram_caption_keeps_paragraph_breaks(self):
        fitted = _fit_text("アメリカで検索急上昇\n\n使う場面を確認", "instagram", "")
        self.assertIn("\n\n", fitted)
        self.assertTrue(fitted.endswith("広告を含みます。"))

    def test_x_daily_plan_has_twelve_slots_and_three_link_slots(self):
        self.assertEqual(12, len(X_DAILY_SLOTS_JST))
        scheduled = [
            datetime(2030, 1, 1, hour - 9 if hour >= 9 else hour + 15, minute, tzinfo=timezone.utc).isoformat()
            for hour, minute in X_DAILY_SLOTS_JST
        ]
        self.assertEqual(3, sum(_x_schedule_has_link(value) for value in scheduled))

    def test_x_without_link_does_not_append_empty_url(self):
        fitted = _fit_text("韓国で注目される理由を確認", "x", "")
        self.assertNotIn("http", fitted)
        self.assertIn("気になる方は固定ポストへ", fitted)
        self.assertTrue(fitted.endswith("※広告を含む記事です"))

    def test_dry_run_does_not_mark_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = settings_for(root)
            initialize(settings.database_path)
            content_id = seed_content(settings)
            with transaction(settings.database_path) as conn:
                enqueue_social_assets(conn, settings, content_id, "article-1", {"x": ["投稿"], "threads": [], "instagram": []})
            approve_posts(settings, [], approve_all=True)
            post_id = list_queue(settings, platform="x")[0]["id"]
            reschedule_post(settings, post_id, "2020-01-01T00:00:00+00:00")
            result = dispatch(settings, live=False)
            self.assertEqual(result[0]["mode"], "dry-run")
            with connect(settings.database_path) as conn:
                self.assertEqual(conn.execute("SELECT status FROM social_posts").fetchone()["status"], "ready")

    def test_import_manual_social_posts_from_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = settings_for(root)
            initialize(settings.database_path)
            csv_path = root / "manual.csv"
            csv_path.write_text(
                "post_no,stage,theme,post_text,status,posted_url,notes\n"
                "1,認知,AI,短い投稿,ready,,\n"
                "2,信用,充電器,投稿済みは飛ばす,posted,https://x.com/example/status/1,\n",
                encoding="utf-8",
            )
            result = import_manual_social_posts(settings, csv_path, platform="x", approve=True)
            self.assertEqual(result["inserted"], 1)
            self.assertEqual(result["skipped"], 1)
            rows = list_queue(settings, platform="x")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["approval_status"], "approved")
            self.assertEqual(rows[0]["status"], "ready")

    def test_mark_manual_post_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = settings_for(root)
            initialize(settings.database_path)
            csv_path = root / "manual.csv"
            csv_path.write_text(
                "post_no,stage,theme,post_text,status,posted_url,notes\n"
                "1,認知,AI,短い投稿,ready,,\n",
                encoding="utf-8",
            )
            import_manual_social_posts(settings, csv_path, platform="x", approve=True)
            post_id = list_queue(settings, platform="x")[0]["id"]
            self.assertTrue(mark_post_published(settings, post_id, "https://x.com/example/status/1"))
            row = list_queue(settings, platform="x")[0]
            self.assertEqual(row["status"], "published")
            self.assertEqual(row["permalink"], "https://x.com/example/status/1")

    def test_discord_ready_message_contains_copy_text_and_record_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = settings_for(root)
            initialize(settings.database_path)
            csv_path = root / "manual.csv"
            csv_path.write_text(
                "post_no,stage,theme,post_text,status,posted_url,notes\n"
                "1,認知,AI,短い投稿,ready,,\n",
                encoding="utf-8",
            )
            import_manual_social_posts(settings, csv_path, platform="x", approve=True)
            messages = discord_ready_messages(settings, platform="x", limit=1, account_url="https://x.com/example")
            self.assertEqual(len(messages), 1)
            content = str(messages[0]["content"])
            self.assertIn("https://x.com/compose/post", content)
            self.assertIn("https://twitter.com/intent/tweet?text=", content)
            self.assertIn("短い投稿", content)
            self.assertIn("social-mark-published", content)

    def test_discord_ready_messages_skip_successfully_notified_post(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = settings_for(root)
            initialize(settings.database_path)
            csv_path = root / "manual.csv"
            csv_path.write_text(
                "post_no,stage,theme,post_text,status,posted_url,notes\n"
                "1,認知,AI,最初の投稿,ready,,\n"
                "2,比較,AI,次の投稿,ready,,\n",
                encoding="utf-8",
            )
            import_manual_social_posts(settings, csv_path, platform="x", approve=True)
            first_id = discord_ready_messages(settings, platform="x", limit=1)[0]["id"]
            with transaction(settings.database_path) as conn:
                conn.execute(
                    "INSERT INTO social_post_attempts(social_post_id, mode, status) VALUES (?, 'discord', 'success')",
                    (first_id,),
                )
            next_message = discord_ready_messages(settings, platform="x", limit=1)
            self.assertEqual(len(next_message), 1)
            self.assertNotEqual(next_message[0]["id"], first_id)
            self.assertIn("次の投稿", str(next_message[0]["content"]))

    def test_live_dispatch_stops_on_placeholder_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = settings_for(root)
            initialize(settings.database_path)
            content_id = seed_content(settings)
            with transaction(settings.database_path) as conn:
                enqueue_social_assets(conn, settings, content_id, "article-1", {"x": ["投稿"], "threads": [], "instagram": []})
            approve_posts(settings, [], approve_all=True)
            post_id = list_queue(settings, platform="x")[0]["id"]
            reschedule_post(settings, post_id, "2020-01-01T00:00:00+00:00")
            with transaction(settings.database_path) as conn:
                conn.execute("UPDATE social_posts SET target_url='{ARTICLE_URL:article-1}' WHERE id=?", (post_id,))
            with self.assertRaisesRegex(ValueError, "SITE_BASE_URL"):
                dispatch(settings, live=True)

    def test_reject_updates_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = settings_for(root)
            initialize(settings.database_path)
            content_id = seed_content(settings)
            with transaction(settings.database_path) as conn:
                enqueue_social_assets(conn, settings, content_id, "article-1", {"x": ["投稿"], "threads": [], "instagram": []})
            post_id = list_queue(settings)[0]["id"]
            self.assertTrue(reject_post(settings, post_id, "表現修正"))
            self.assertEqual(list_queue(settings)[0]["status"], "rejected")

    def test_media_reschedule_and_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = settings_for(root)
            initialize(settings.database_path)
            content_id = seed_content(settings)
            with transaction(settings.database_path) as conn:
                enqueue_social_assets(
                    conn, settings, content_id, "article-1",
                    {"x": ["投稿"], "threads": [], "instagram": ["1枚目", "2枚目"]},
                )
            rows = list_queue(settings)
            x_id = next(row["id"] for row in rows if row["platform"] == "x")
            ig_id = next(row["id"] for row in rows if row["platform"] == "instagram")
            self.assertTrue(set_media_urls(settings, ig_id, ["https://example.com/slide-1.png"]))
            self.assertTrue(reschedule_post(settings, x_id, "2030-01-02T03:04:05+09:00"))
            approve_posts(settings, [x_id])
            with transaction(settings.database_path) as conn:
                conn.execute("UPDATE social_posts SET status='failed' WHERE id=?", (x_id,))
            self.assertTrue(retry_post(settings, x_id))
            updated = {row["id"]: row for row in list_queue(settings)}
            self.assertEqual(updated[x_id]["status"], "ready")
            self.assertEqual(updated[x_id]["scheduled_at"], "2030-01-01T18:04:05+00:00")
            self.assertEqual(updated[ig_id]["status"], "queued")


if __name__ == "__main__":
    unittest.main()
