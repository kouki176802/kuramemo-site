from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Sequence, Tuple

from .models import Offer, ScoreBreakdown
from .settings import Settings
from .utils import contains_any, normalize_text


PURCHASE_TRIGGERS = {
    "発売": 7,
    "発表": 5,
    "新機能": 7,
    "値上げ": 9,
    "値下げ": 9,
    "セール": 10,
    "予約": 8,
    "再入荷": 9,
    "品薄": 8,
    "予報": 7,
    "猛暑": 9,
    "梅雨": 7,
    "台風": 6,
    "新生活": 8,
    "比較": 6,
}

LONG_LIVED_TERMS = ["選び方", "比較", "新生活", "猛暑", "梅雨", "防災", "料金改定", "新機能"]
HIGH_RISK_TERMS = ["治療", "診断", "処方", "必ず儲かる", "死亡", "殺人", "事故", "被災者"]


def _age_hours(published_at: str) -> float:
    if not published_at:
        return 24.0
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600)
    except ValueError:
        return 24.0


def score_event(
    settings: Settings,
    title: str,
    summary: str,
    offers: Sequence[Tuple[Offer, int, List[str]]],
    source_count: int,
    published_at: str,
    source_trust: int,
) -> ScoreBreakdown:
    text = normalize_text("%s %s" % (title, summary))
    reasons: List[str] = []
    risk_flags = contains_any(text, list(settings.banned_topics) + HIGH_RISK_TERMS)

    purchase_raw = 0
    for term, points in PURCHASE_TRIGGERS.items():
        if normalize_text(term) in text:
            purchase_raw += points
            reasons.append("購買トリガー:%s" % term)
    purchase_intent = min(25, 7 + purchase_raw)

    offer_fit = min(20, len(offers) * 6 + (2 if offers else 0))
    if offers:
        reasons.append("商品候補:%d件" % len(offers))

    velocity = min(15, source_count * 4 + source_trust)
    revenue_values = [offer.reward_value for offer, _, _ in offers]
    revenue = min(15, (6 if offers else 0) + int(max(revenue_values or [0]) > 0) * 4 + min(len(offers), 5))

    age = _age_hours(published_at)
    speed = 10 if age <= 6 else 8 if age <= 24 else 5 if age <= 72 else 2
    longevity = 5 if contains_any(text, LONG_LIVED_TERMS) else 2
    competition = 3
    safety = 0 if risk_flags else 5

    total = purchase_intent + offer_fit + velocity + revenue + speed + longevity + competition + safety
    if risk_flags:
        reasons.append("高リスクのため自動公開禁止")
    if source_trust >= 4:
        reasons.append("高信頼ソース")

    return ScoreBreakdown(
        purchase_intent=purchase_intent,
        offer_fit=offer_fit,
        velocity=velocity,
        revenue=revenue,
        speed=speed,
        longevity=longevity,
        competition=competition,
        safety=safety,
        total=min(total, 100),
        reasons=reasons,
        risk_flags=risk_flags,
    )


def score_to_json(score: ScoreBreakdown) -> str:
    return json.dumps(score.__dict__, ensure_ascii=False, sort_keys=True)

