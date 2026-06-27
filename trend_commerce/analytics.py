from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict

from .database import transaction
from .settings import Settings
from .utils import stable_hash


REQUIRED_CONVERSION_COLUMNS = {
    "transaction_id", "network", "offer_id", "occurred_at", "status", "amount", "content_slug"
}


def import_conversions(settings: Settings, path: Path) -> Dict[str, int]:
    raw = path.read_bytes()
    file_hash = stable_hash(raw.decode("utf-8-sig"))
    inserted = 0
    skipped = 0
    with path.open(encoding="utf-8-sig", newline="") as handle, transaction(settings.database_path) as conn:
        reader = csv.DictReader(handle)
        missing = REQUIRED_CONVERSION_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError("売上CSVに必須列がありません: %s" % ", ".join(sorted(missing)))
        existing_batch = conn.execute("SELECT id FROM import_batches WHERE file_hash=?", (file_hash,)).fetchone()
        if existing_batch:
            return {"inserted": 0, "skipped": sum(1 for _ in reader), "duplicate_batch": 1}
        rows = list(reader)
        for row in rows:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO conversions(
                    transaction_id, network, offer_id, occurred_at, status, amount, content_slug
                ) VALUES (?, ?, NULLIF(?, ''), ?, ?, ?, ?)
                """,
                (
                    row["transaction_id"], row["network"], row["offer_id"], row["occurred_at"],
                    row["status"], float(row["amount"] or 0), row["content_slug"],
                ),
            )
            inserted += int(cursor.rowcount > 0)
            skipped += int(cursor.rowcount == 0)
        conn.execute(
            "INSERT INTO import_batches(source, file_hash, row_count) VALUES (?, ?, ?)",
            (path.name, file_hash, len(rows)),
        )
    return {"inserted": inserted, "skipped": skipped, "duplicate_batch": 0}


def add_metric(
    settings: Settings,
    content_id: int,
    measured_at: str,
    sessions: int,
    outbound_clicks: int,
    conversions: int,
    revenue: float,
    source: str = "manual",
) -> None:
    with transaction(settings.database_path) as conn:
        conn.execute(
            """
            INSERT INTO metrics_hourly(content_id, measured_at, sessions, outbound_clicks, conversions, revenue, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(content_id, measured_at, source) DO UPDATE SET
                sessions=excluded.sessions,
                outbound_clicks=excluded.outbound_clicks,
                conversions=excluded.conversions,
                revenue=excluded.revenue
            """,
            (content_id, measured_at, sessions, outbound_clicks, conversions, revenue, source),
        )

