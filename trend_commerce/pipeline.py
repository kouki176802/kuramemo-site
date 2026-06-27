from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .catalog import match_offers
from .clustering import cluster_pending_signals
from .compliance import check_article
from .database import connect, transaction
from .generation import choose_generator
from .models import EventCandidate, ScoreBreakdown
from .scoring import score_event, score_to_json
from .settings import Settings, ensure_directories
from .social import enqueue_social_assets
from .utils import now_iso


def _event_context(conn, event_id: int):
    return conn.execute(
        """
        SELECT te.*,
               COUNT(es.signal_id) AS source_count,
               MAX(COALESCE(s.trust_level, 3)) AS source_trust,
               MAX(rs.published_at) AS published_at
        FROM trend_events te
        LEFT JOIN event_sources es ON es.event_id = te.id
        LEFT JOIN raw_signals rs ON rs.id = es.signal_id
        LEFT JOIN sources s ON s.id = rs.source_id
        WHERE te.id = ?
        GROUP BY te.id
        """,
        (event_id,),
    ).fetchone()


def score_all_events(settings: Settings) -> int:
    count = 0
    with transaction(settings.database_path) as conn:
        rows = conn.execute("SELECT id FROM trend_events WHERE status IN ('detected', 'scored')").fetchall()
        for id_row in rows:
            row = _event_context(conn, int(id_row["id"]))
            matches = match_offers(settings, row["title"], row["summary"], row["category"])
            score = score_event(
                settings=settings,
                title=row["title"],
                summary=row["summary"],
                offers=matches,
                source_count=int(row["source_count"] or 1),
                published_at=row["published_at"] or "",
                source_trust=int(row["source_trust"] or 3),
            )
            conn.execute(
                "UPDATE trend_events SET score_total=?, score_json=?, risk_flags=?, status='scored' WHERE id=?",
                (score.total, score_to_json(score), json.dumps(score.risk_flags, ensure_ascii=False), row["id"]),
            )
            conn.execute("DELETE FROM event_offer_matches WHERE event_id=?", (row["id"],))
            for offer, match_score, reasons in matches:
                conn.execute(
                    """
                    INSERT INTO event_offer_matches(event_id, offer_id, match_score, reasons)
                    VALUES (?, ?, ?, ?)
                    """,
                    (row["id"], offer.offer_id, match_score, json.dumps(reasons, ensure_ascii=False)),
                )
            count += 1
    return count


def _load_candidate(settings: Settings, event_id: int) -> EventCandidate:
    with connect(settings.database_path) as conn:
        row = _event_context(conn, event_id)
        urls = [
            item["url"]
            for item in conn.execute(
                """
                SELECT rs.url FROM event_sources es
                JOIN raw_signals rs ON rs.id=es.signal_id
                WHERE es.event_id=? ORDER BY rs.collected_at
                """,
                (event_id,),
            )
        ]
        matches = match_offers(settings, row["title"], row["summary"], row["category"])
        score_data = json.loads(row["score_json"])
        return EventCandidate(
            event_id=event_id,
            title=row["title"],
            summary=row["summary"],
            category=row["category"],
            source_urls=urls,
            first_seen_at=row["first_seen_at"],
            published_at=row["published_at"],
            score=ScoreBreakdown(**score_data),
            offers=[offer for offer, _, _ in matches],
        )


def generate_drafts(settings: Settings, allow_paid: bool = False, limit: Optional[int] = None) -> List[Path]:
    ensure_directories(settings)
    max_items = limit or settings.max_candidates_per_run
    with connect(settings.database_path) as conn:
        rows = conn.execute(
            """
            SELECT te.id FROM trend_events te
            LEFT JOIN content_items ci ON ci.event_id=te.id AND ci.content_type='article'
            WHERE te.status='scored' AND te.score_total>=? AND ci.id IS NULL
            ORDER BY te.score_total DESC, te.first_seen_at
            LIMIT ?
            """,
            (settings.draft_threshold, max_items),
        ).fetchall()

    generator = choose_generator(settings, allow_paid=allow_paid)
    created: List[Path] = []
    for row in rows:
        candidate = _load_candidate(settings, int(row["id"]))
        bundle = generator.generate(candidate)
        compliance = check_article(settings, bundle)
        draft_path = settings.output_dir / "drafts" / (bundle.slug + ".md")
        social_path = settings.output_dir / "social" / (bundle.slug + ".json")
        draft_path.write_text(bundle.body_markdown, encoding="utf-8")
        social_path.write_text(json.dumps(bundle.social_assets, ensure_ascii=False, indent=2), encoding="utf-8")

        with transaction(settings.database_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO content_items(event_id, content_type, title, slug, file_path, status, generator)
                VALUES (?, 'article', ?, ?, ?, ?, ?)
                """,
                (
                    candidate.event_id, bundle.title, bundle.slug, str(draft_path.relative_to(settings.output_dir.parent)),
                    compliance.decision, generator.name,
                ),
            )
            content_id = int(cursor.lastrowid)
            conn.execute(
                """
                INSERT INTO compliance_reports(
                    content_id, factual_score, trust_score, dark_pattern_score, decision, issues
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    content_id, compliance.factual_score, compliance.trust_score,
                    compliance.dark_pattern_score, compliance.decision,
                    json.dumps(compliance.issues, ensure_ascii=False),
                ),
            )
            if compliance.decision == "approval_required":
                enqueue_social_assets(conn, settings, content_id, bundle.slug, bundle.social_assets)
            conn.execute("UPDATE trend_events SET status='drafted' WHERE id=?", (candidate.event_id,))
        created.append(draft_path)
    return created


def run_pipeline(settings: Settings, allow_paid: bool = False) -> Dict[str, object]:
    counters: Dict[str, object] = {"clustered": 0, "scored": 0, "drafts": 0, "files": []}
    with transaction(settings.database_path) as conn:
        run_id = int(conn.execute("INSERT INTO bot_runs(job_name, status) VALUES ('pipeline', 'running')").lastrowid)
    try:
        counters["clustered"] = cluster_pending_signals(settings)
        counters["scored"] = score_all_events(settings)
        files = generate_drafts(settings, allow_paid=allow_paid)
        counters["drafts"] = len(files)
        counters["files"] = [str(path) for path in files]
        with transaction(settings.database_path) as conn:
            conn.execute(
                "UPDATE bot_runs SET status='completed', finished_at=?, counters=? WHERE id=?",
                (now_iso(), json.dumps(counters, ensure_ascii=False), run_id),
            )
        return counters
    except Exception as exc:
        with transaction(settings.database_path) as conn:
            conn.execute(
                "UPDATE bot_runs SET status='failed', finished_at=?, counters=?, error=? WHERE id=?",
                (now_iso(), json.dumps(counters, ensure_ascii=False), str(exc), run_id),
            )
        raise
