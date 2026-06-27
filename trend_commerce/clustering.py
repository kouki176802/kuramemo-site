from __future__ import annotations

from typing import Dict, List

from .database import transaction
from .settings import Settings
from .utils import normalize_text, now_iso, similarity


def _choose_category(title: str, summary: str, hint: str) -> str:
    text = normalize_text("%s %s" % (title, summary))
    mappings: Dict[str, List[str]] = {
        "季節・暮らし": ["猛暑", "梅雨", "台風", "寒波", "防災", "新生活", "旅行", "家電", "食品"],
        "美容": ["美容", "コスメ", "スキンケア", "化粧品", "脱毛器", "ヘアワックス", "シェーバー"],
        "フィットネス": ["筋トレ", "プロテイン", "クレアチン", "eaa", "bcaa", "フィットネス"],
        "健康": ["健康", "ビタミン", "食物繊維", "乳酸菌", "サプリメント", "栄養補助"],
        "AI・ガジェット": ["ai", "スマホ", "pc", "アプリ", "ガジェット", "イヤホン", "サブスク"],
    }
    best = ("季節・暮らし", 0)
    for category, terms in mappings.items():
        points = sum(1 for term in terms if normalize_text(term) in text)
        if points > best[1]:
            best = (category, points)
    if best[1] > 0:
        return best[0]
    return hint or "季節・暮らし"


def cluster_pending_signals(settings: Settings, threshold: float = 0.42) -> int:
    processed = 0
    with transaction(settings.database_path) as conn:
        signals = conn.execute(
            """
            SELECT rs.*, COALESCE(s.category, '') AS category_hint
            FROM raw_signals rs
            LEFT JOIN sources s ON s.id = rs.source_id
            WHERE rs.processed_at IS NULL
            ORDER BY rs.collected_at, rs.id
            """
        ).fetchall()
        for signal in signals:
            candidates = conn.execute(
                "SELECT id, title, summary FROM trend_events ORDER BY last_seen_at DESC LIMIT 100"
            ).fetchall()
            best_id = None
            best_similarity = 0.0
            signal_text = "%s %s" % (signal["title"], signal["summary"])
            for candidate in candidates:
                value = similarity(signal_text, "%s %s" % (candidate["title"], candidate["summary"]))
                if value > best_similarity:
                    best_similarity = value
                    best_id = int(candidate["id"])

            timestamp = now_iso()
            if best_id is not None and best_similarity >= threshold:
                event_id = best_id
                conn.execute("UPDATE trend_events SET last_seen_at = ? WHERE id = ?", (timestamp, event_id))
            else:
                category = _choose_category(signal["title"], signal["summary"], signal["category_hint"])
                cursor = conn.execute(
                    """
                    INSERT INTO trend_events(canonical_topic, title, summary, category, first_seen_at, last_seen_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalize_text(signal["title"]), signal["title"], signal["summary"], category,
                        timestamp, timestamp,
                    ),
                )
                event_id = int(cursor.lastrowid)
            conn.execute(
                "INSERT OR IGNORE INTO event_sources(event_id, signal_id) VALUES (?, ?)",
                (event_id, signal["id"]),
            )
            conn.execute("UPDATE raw_signals SET processed_at = ? WHERE id = ?", (timestamp, signal["id"]))
            processed += 1
    return processed
