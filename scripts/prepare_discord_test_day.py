"""Prepare one clean 12-slot X/Discord test day from reviewed post IDs."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trend_commerce.database import transaction
from trend_commerce.settings import load_settings
from trend_commerce.social import (
    JST,
    URL_PATTERN,
    X_DAILY_SLOTS_JST,
    X_LINK_SLOT_INDEXES,
    _fit_text,
)
from trend_commerce.utils import normalize_text, stable_hash


def _base_text(value: str) -> str:
    text = URL_PATTERN.sub("", value)
    text = text.replace("※広告を含む記事です", "")
    text = text.replace("気になる方は固定ポストへ", "")
    text = re.sub(r"(?:なぜ注目？\s*){2,}", "なぜ注目？ ", text)
    return re.sub(r"\s+", " ", text).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, action="append", required=True)
    parser.add_argument("--date", help="Asia/Tokyoの日付 YYYY-MM-DD。既定は翌日")
    args = parser.parse_args()
    if len(args.id) != 12 or len(set(args.id)) != 12:
        parser.error("異なる投稿IDを12件指定してください")

    settings = load_settings()
    target_day = date.fromisoformat(args.date) if args.date else datetime.now(JST).date() + timedelta(days=1)
    with transaction(settings.database_path) as conn:
        placeholders = ",".join("?" for _ in args.id)
        rows = conn.execute(
            "SELECT id, platform, post_text, target_url FROM social_posts WHERE id IN (%s)" % placeholders,
            args.id,
        ).fetchall()
        by_id = {int(row["id"]): row for row in rows}
        if set(by_id) != set(args.id):
            parser.error("存在しない投稿IDがあります")
        if any(str(row["platform"]) != "x" for row in rows):
            parser.error("X投稿以外のIDが含まれています")

        conn.execute(
            """
            UPDATE social_posts SET status='experiment_hold', updated_at=CURRENT_TIMESTAMP
            WHERE platform='x' AND status='ready' AND approval_status='approved'
              AND NOT EXISTS (
                SELECT 1 FROM social_post_attempts a
                WHERE a.social_post_id=social_posts.id AND a.mode='discord' AND a.status='success'
              )
            """
        )
        for index, post_id in enumerate(args.id):
            row = by_id[post_id]
            hour, minute = X_DAILY_SLOTS_JST[index]
            scheduled = datetime(
                target_day.year, target_day.month, target_day.day, hour, minute, tzinfo=JST
            ).astimezone(timezone.utc).isoformat()
            target_url = str(row["target_url"] or "") if index in X_LINK_SLOT_INDEXES else ""
            if index in X_LINK_SLOT_INDEXES and not target_url:
                parser.error("URL枠にリンクのない投稿ID %s が割り当てられています" % post_id)
            post_text = _fit_text(_base_text(str(row["post_text"])), "x", target_url)
            fingerprint = stable_hash("x", normalize_text(post_text), target_url)
            conn.execute(
                """
                UPDATE social_posts
                SET post_text=?, target_url=?, fingerprint=?, scheduled_at=?,
                    status='ready', approval_status='approved', updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (post_text, target_url, fingerprint, scheduled, post_id),
            )
    print("Discord 12投稿テストを準備: %s" % target_day.isoformat())


if __name__ == "__main__":
    main()
