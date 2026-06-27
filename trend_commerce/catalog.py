from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .database import connect, transaction
from .models import Offer
from .settings import ROOT, Settings
from .utils import normalize_text, split_pipe


def import_offers(settings: Settings, path: Optional[Path] = None) -> int:
    csv_path = path or ROOT / "data" / "offers.csv"
    count = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as handle, transaction(settings.database_path) as conn:
        for row in csv.DictReader(handle):
            conn.execute(
                """
                INSERT INTO offers(
                    offer_id, network, name, category, keywords, problem_tags, event_tags,
                    affiliate_url, landing_url, reward_type, reward_value,
                    allowed_media, status, last_verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(offer_id) DO UPDATE SET
                    network=excluded.network, name=excluded.name, category=excluded.category,
                    keywords=excluded.keywords, problem_tags=excluded.problem_tags,
                    event_tags=excluded.event_tags, affiliate_url=excluded.affiliate_url,
                    landing_url=excluded.landing_url, reward_type=excluded.reward_type,
                    reward_value=excluded.reward_value, allowed_media=excluded.allowed_media,
                    status=excluded.status, last_verified_at=excluded.last_verified_at
                """,
                (
                    row["offer_id"], row["network"], row["name"], row["category"],
                    json.dumps(split_pipe(row["keywords"]), ensure_ascii=False),
                    json.dumps(split_pipe(row["problem_tags"]), ensure_ascii=False),
                    json.dumps(split_pipe(row["event_tags"]), ensure_ascii=False),
                    row["affiliate_url"], row["landing_url"], row["reward_type"],
                    float(row["reward_value"] or 0),
                    json.dumps(split_pipe(row["allowed_media"]), ensure_ascii=False),
                    row["status"], row["last_verified_at"],
                ),
            )
            count += 1
    return count


def upsert_offer_csv(values: Dict[str, str], path: Optional[Path] = None) -> None:
    csv_path = path or ROOT / "data" / "offers.csv"
    fieldnames = [
        "offer_id", "network", "name", "category", "keywords", "problem_tags", "event_tags",
        "affiliate_url", "landing_url", "reward_type", "reward_value", "allowed_media", "status", "last_verified_at",
    ]
    rows: List[Dict[str, str]] = []
    if csv_path.exists():
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    normalized = {field: values.get(field, "") for field in fieldnames}
    replaced = False
    for index, row in enumerate(rows):
        if row.get("offer_id") == normalized["offer_id"]:
            rows[index] = normalized
            replaced = True
            break
    if not replaced:
        rows.append(normalized)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _row_to_offer(row) -> Offer:
    return Offer(
        offer_id=row["offer_id"],
        network=row["network"],
        name=row["name"],
        category=row["category"],
        keywords=json.loads(row["keywords"]),
        problem_tags=json.loads(row["problem_tags"]),
        event_tags=json.loads(row["event_tags"]),
        affiliate_url=row["affiliate_url"],
        landing_url=row["landing_url"],
        reward_type=row["reward_type"],
        reward_value=float(row["reward_value"]),
        allowed_media=json.loads(row["allowed_media"]),
        status=row["status"],
        last_verified_at=row["last_verified_at"],
    )


def list_offers(settings: Settings) -> List[Offer]:
    with connect(settings.database_path) as conn:
        return [_row_to_offer(row) for row in conn.execute("SELECT * FROM offers ORDER BY name")]


def match_offers(settings: Settings, title: str, summary: str, category: str = "", limit: int = 5) -> List[Tuple[Offer, int, List[str]]]:
    text = normalize_text("%s %s" % (title, summary))
    matches: List[Tuple[Offer, int, List[str]]] = []
    for offer in list_offers(settings):
        reasons: List[str] = []
        text_score = 0
        for term in offer.keywords:
            if normalize_text(term) in text:
                text_score += 30
                reasons.append("キーワード:%s" % term)
        for term in offer.problem_tags:
            if normalize_text(term) in text:
                text_score += 20
                reasons.append("悩み:%s" % term)
        for term in offer.event_tags:
            if normalize_text(term) in text:
                text_score += 25
                reasons.append("イベント:%s" % term)
        if text_score == 0:
            continue
        score = text_score
        if category and offer.category == category:
            score += 10
            reasons.append("カテゴリ一致")
        matches.append((offer, min(score, 100), reasons))
    matches.sort(key=lambda item: (-item[1], -item[0].reward_value, item[0].name))
    return matches[:limit]
