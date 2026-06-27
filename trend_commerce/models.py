from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class Source:
    name: str
    url: str
    kind: str = "rss"
    category: str = ""
    trust_level: int = 3
    active: bool = True


@dataclass
class Signal:
    title: str
    url: str
    summary: str
    published_at: Optional[datetime]
    source_name: str
    source_trust: int = 3
    category_hint: str = ""


@dataclass
class Offer:
    offer_id: str
    network: str
    name: str
    category: str
    keywords: List[str]
    problem_tags: List[str]
    event_tags: List[str]
    affiliate_url: str
    landing_url: str
    reward_type: str
    reward_value: float
    allowed_media: List[str]
    status: str
    last_verified_at: str


@dataclass
class ScoreBreakdown:
    purchase_intent: int
    offer_fit: int
    velocity: int
    revenue: int
    speed: int
    longevity: int
    competition: int
    safety: int
    total: int
    reasons: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)


@dataclass
class EventCandidate:
    event_id: int
    title: str
    summary: str
    category: str
    source_urls: List[str]
    first_seen_at: str
    published_at: Optional[str]
    score: ScoreBreakdown
    offers: List[Offer]


@dataclass
class ArticleBundle:
    title: str
    slug: str
    meta_description: str
    lead: str
    body_markdown: str
    cta_blocks: List[Dict[str, str]]
    social_assets: Dict[str, List[str]]
    behavioral_principles: List[str]
    objections: List[str]
    non_purchase_option: str
    urgency_source: str
    evidence_urls: List[str]

