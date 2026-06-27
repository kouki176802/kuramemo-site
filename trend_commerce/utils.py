from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import datetime, timezone
from typing import Iterable, List, Set
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
}

IMPORTANT_TERMS = [
    "猛暑", "熱帯夜", "梅雨", "台風", "寒波", "花粉", "黄砂", "防災", "停電",
    "新生活", "旅行", "値上げ", "値下げ", "セール", "再入荷", "品薄", "発売",
    "ai", "生成ai", "新機能", "スマホ", "pc", "アプリ", "イヤホン", "サブスク",
    "美容", "コスメ", "スキンケア", "筋トレ", "プロテイン", "ダイエット",
]

GENERIC_TERMS = {"ai", "生成ai", "アプリ", "スマホ", "pc", "美容", "家電", "旅行"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonicalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(sorted(query)), ""))


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "").lower()
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[\s\u3000]+", " ", value)
    value = re.sub(r"[^0-9a-zぁ-んァ-ヶ一-龠ー ]", "", value)
    return value.strip()


def strip_markup(text: str, limit: int = 2000) -> str:
    value = html.unescape(text or "")
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[\s\u3000]+", " ", value).strip()
    return value[:limit]


def stable_hash(*values: str) -> str:
    joined = "\x1f".join(values)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def char_ngrams(text: str, size: int = 2) -> Set[str]:
    normalized = normalize_text(text).replace(" ", "")
    if len(normalized) <= size:
        return {normalized} if normalized else set()
    return {normalized[i : i + size] for i in range(len(normalized) - size + 1)}


def similarity(left: str, right: str) -> float:
    a, b = char_ngrams(left), char_ngrams(right)
    if not a or not b:
        return 0.0
    jaccard = len(a & b) / len(a | b)
    left_normalized = normalize_text(left)
    right_normalized = normalize_text(right)
    shared_terms = [
        term for term in IMPORTANT_TERMS
        if normalize_text(term) in left_normalized and normalize_text(term) in right_normalized
    ]
    if not shared_terms:
        term_score = 0.0
    elif len(shared_terms) == 1 and normalize_text(shared_terms[0]) in GENERIC_TERMS:
        term_score = 0.25
    else:
        term_score = min(0.8, 0.35 + 0.1 * len(shared_terms))
    return max(jaccard, term_score)


def split_pipe(value: str) -> List[str]:
    return [part.strip() for part in (value or "").split("|") if part.strip()]


def contains_any(text: str, terms: Iterable[str]) -> List[str]:
    normalized = normalize_text(text)
    found: List[str] = []
    seen = set()
    for term in terms:
        normalized_term = normalize_text(term)
        if normalized_term and normalized_term in normalized and normalized_term not in seen:
            found.append(term)
            seen.add(normalized_term)
    return found


def safe_slug(prefix: str, identifier: int, title: str) -> str:
    digest = stable_hash(title)[:8]
    clean_prefix = re.sub(r"[^a-z0-9-]", "", prefix.lower()) or "item"
    return "%s-%s-%s" % (clean_prefix, identifier, digest)
