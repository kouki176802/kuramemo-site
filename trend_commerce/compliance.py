from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .models import ArticleBundle
from .settings import Settings
from .utils import contains_any, normalize_text


@dataclass
class ComplianceResult:
    factual_score: int
    trust_score: int
    dark_pattern_score: int
    decision: str
    issues: List[str]


REQUIRED_MARKERS = ["広告について", "買わない場合の代替案", "出典・確認日時"]
UNSUPPORTED_EXPERIENCE = ["使ってみた", "実際に使った", "効果があった", "愛用しています"]


def check_article(settings: Settings, bundle: ArticleBundle) -> ComplianceResult:
    text = "%s\n%s" % (bundle.title, bundle.body_markdown)
    issues: List[str] = []

    missing_markers = [marker for marker in REQUIRED_MARKERS if marker not in text]
    for marker in missing_markers:
        issues.append("必須表示なし:%s" % marker)

    dark_hits = contains_any(text, settings.dark_pattern_terms)
    for term in dark_hits:
        issues.append("ダークパターン候補:%s" % term)

    experience_hits = contains_any(text, UNSUPPORTED_EXPERIENCE)
    for term in experience_hits:
        issues.append("未検証の体験表現:%s" % term)

    banned_hits = contains_any(text, settings.banned_topics)
    for term in banned_hits:
        issues.append("禁止テーマ:%s" % term)

    urgency_terms = contains_any(text, ["今すぐ", "急いで", "期限", "残り"])
    if urgency_terms and not bundle.urgency_source:
        issues.append("緊急性の出典なし")

    if not bundle.evidence_urls:
        issues.append("出典URLなし")
    if not bundle.non_purchase_option:
        issues.append("買わない選択肢なし")
    if len(bundle.objections) < 3:
        issues.append("反論処理が不足")

    factual_score = 100
    if not bundle.evidence_urls:
        factual_score -= 40
    factual_score -= 15 * len(banned_hits)
    factual_score -= 10 * len(experience_hits)

    trust_score = 100 - 15 * len(missing_markers)
    if not bundle.non_purchase_option:
        trust_score -= 20
    if not bundle.cta_blocks:
        trust_score -= 5

    dark_pattern_score = min(100, len(dark_hits) * 30 + (20 if urgency_terms and not bundle.urgency_source else 0))

    if banned_hits:
        decision = "blocked"
    elif factual_score < 90 or trust_score < 80 or dark_pattern_score > 10:
        decision = "revision_required"
    else:
        decision = "approval_required"

    return ComplianceResult(
        factual_score=max(0, factual_score),
        trust_score=max(0, trust_score),
        dark_pattern_score=dark_pattern_score,
        decision=decision,
        issues=issues,
    )

