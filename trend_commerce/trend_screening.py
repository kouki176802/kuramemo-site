from __future__ import annotations

import csv
import json
import math
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .database import initialize, transaction
from .rakuten import RakutenProduct, RakutenProductClient
from .settings import ROOT, Settings
from .social import _fit_text, _next_schedule
from .utils import normalize_text, stable_hash


TRENDS_URL = "https://trends.google.com/trending/rss?geo=%s"
TRENDS_NAMESPACE = {"ht": "https://trends.google.com/trending/rss"}
COUNTRIES = {
    "JP": "日本",
    "US": "アメリカ",
    "KR": "韓国",
    "GB": "イギリス",
}
BLOCKED_NEWS_TERMS = {
    "殺害", "死亡", "逮捕", "虐待", "性被害", "被害者", "被疑者", "容疑者",
    "がん公表", "闘病", "訃報", "自殺", "暴行", "誘拐",
}


@dataclass(frozen=True)
class TrendRule:
    rule_id: str
    category: str
    page_slug: str
    context: str
    audience: str
    trigger_terms: List[str]
    product_terms: List[str]
    genre_id: str
    genre_name: str


@dataclass(frozen=True)
class TrendObservation:
    fingerprint: str
    source_name: str
    country_code: str
    country_name: str
    topic: str
    approx_traffic: str
    news_title: str
    news_url: str
    news_source: str
    published_at: str
    rule_hint: str = ""

    @property
    def evidence_text(self) -> str:
        market = _market_label(self.country_code, self.country_name, self.source_name)
        if self.source_name == "Google News":
            return "【%s】Googleニュースで「%s」を確認。%sが報道" % (
                market,
                _shorten(self.news_title or self.topic, 58),
                self.news_source or "関連メディア",
            )
        traffic = "（検索規模 %s）" % self.approx_traffic if self.approx_traffic else ""
        lead = "【%s】Googleトレンドで「%s」が急上昇%s" % (
            market, self.topic, traffic,
        )
        if self.news_title:
            return "%s。%sが「%s」と報道" % (
                lead, self.news_source or "関連メディア", _shorten(self.news_title, 58),
            )
        return lead


@dataclass(frozen=True)
class TrendOpportunity:
    fingerprint: str
    rule: TrendRule
    observation: Optional[TrendObservation]
    product: RakutenProduct
    score: int
    why_trending: str
    evidence_label: str
    person_note: str

    @property
    def country_name(self) -> str:
        return self.observation.country_name if self.observation else "日本"

    @property
    def topic(self) -> str:
        return self.observation.topic if self.observation else "楽天市場の売れ筋"

    @property
    def trend_scope(self) -> str:
        if not self.observation:
            return "japan_sales"
        return "japan_now" if self.observation.country_code == "JP" else "overseas_watch"

    @property
    def market_label(self) -> str:
        if not self.observation:
            return "日本で売れ筋"
        return _market_label(self.observation.country_code, self.country_name, self.observation.source_name)


def load_trend_rules(path: Optional[Path] = None) -> List[TrendRule]:
    source = path or ROOT / "data" / "trend_topic_rules.csv"
    with source.open(encoding="utf-8-sig", newline="") as handle:
        return [
            TrendRule(
                rule_id=row["rule_id"],
                category=row["category"],
                page_slug=row["page_slug"],
                context=row["context"],
                audience=row["audience"],
                trigger_terms=_split_pipe(row["trigger_terms"]),
                product_terms=_split_pipe(row["product_terms"]),
                genre_id=row["genre_id"],
                genre_name=row["genre_name"],
            )
            for row in csv.DictReader(handle)
        ]


def parse_google_trends(data: bytes, country_code: str) -> List[TrendObservation]:
    root = ET.fromstring(data)
    result: List[TrendObservation] = []
    country_name = COUNTRIES.get(country_code, country_code)
    for item in root.findall("./channel/item"):
        topic = _xml_text(item.find("title"))
        if not topic:
            continue
        traffic = _xml_text(item.find("ht:approx_traffic", TRENDS_NAMESPACE))
        published = _parse_date(_xml_text(item.find("pubDate")))
        news_items = item.findall("ht:news_item", TRENDS_NAMESPACE)
        news_title = ""
        news_url = ""
        news_source = ""
        if news_items:
            news_title = _xml_text(news_items[0].find("ht:news_item_title", TRENDS_NAMESPACE))
            news_url = _xml_text(news_items[0].find("ht:news_item_url", TRENDS_NAMESPACE))
            news_source = _xml_text(news_items[0].find("ht:news_item_source", TRENDS_NAMESPACE))
        fingerprint = stable_hash(
            "google-trends", country_code, topic, published, news_url or news_title,
        )
        result.append(
            TrendObservation(
                fingerprint=fingerprint,
                source_name="Google Trends",
                country_code=country_code,
                country_name=country_name,
                topic=topic,
                approx_traffic=traffic,
                news_title=news_title,
                news_url=news_url,
                news_source=news_source,
                published_at=published,
                rule_hint="",
            )
        )
    return result


def collect_google_trends(countries: Sequence[str]) -> Tuple[List[TrendObservation], List[str]]:
    observations: List[TrendObservation] = []
    errors: List[str] = []
    for country in countries:
        url = TRENDS_URL % country
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "TrendCommerceBot/0.2 (+trend evidence)"})
            with urllib.request.urlopen(request, timeout=12) as response:
                observations.extend(parse_google_trends(response.read(), country))
        except Exception as exc:
            errors.append("%s: %s" % (country, exc))
    return observations, errors


def _collect_rule_news(rule: TrendRule) -> Tuple[List[TrendObservation], List[str]]:
    observations: List[TrendObservation] = []
    errors: List[str] = []
    product_query = " OR ".join(rule.product_terms[:3])
    query = "(%s) (話題 OR 新商品 OR 発売 OR 売れ筋) when:7d" % product_query
    url = "https://news.google.com/rss/search?%s" % urllib.parse.urlencode(
        {"q": query, "hl": "ja", "gl": "JP", "ceid": "JP:ja"}
    )
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "TrendCommerceBot/0.2 (+news evidence)"})
        with urllib.request.urlopen(request, timeout=12) as response:
            root = ET.fromstring(response.read())
    except Exception as exc:
        return [], ["news:%s: %s" % (rule.rule_id, exc)]
    for item in root.findall("./channel/item")[:3]:
        raw_title = _xml_text(item.find("title"))
        link = _xml_text(item.find("link"))
        source = _xml_text(item.find("source"))
        published = _parse_date(_xml_text(item.find("pubDate")))
        if not raw_title or not link:
            continue
        title = raw_title.rsplit(" - ", 1)[0].strip()
        normalized_title = normalize_text(title)
        evidence_terms = rule.product_terms + rule.trigger_terms
        if not any(normalize_text(term) in normalized_title for term in evidence_terms if term):
            continue
        fingerprint = stable_hash("google-news", rule.rule_id, title, link)
        observations.append(
            TrendObservation(
                fingerprint=fingerprint,
                source_name="Google News",
                country_code="JP",
                country_name="日本",
                topic=title,
                approx_traffic="",
                news_title=title,
                news_url=link,
                news_source=source,
                published_at=published,
                rule_hint=rule.rule_id,
            )
        )
    return observations, errors


def collect_product_news(rules: Sequence[TrendRule]) -> Tuple[List[TrendObservation], List[str]]:
    """Collect product-oriented news evidence without calling it search-trending."""
    observations: List[TrendObservation] = []
    errors: List[str] = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_collect_rule_news, rule) for rule in rules]
        for future in as_completed(futures):
            found, failed = future.result()
            observations.extend(found)
            errors.extend(failed)
    return observations, errors


def screen_trend_opportunities(
    settings: Settings,
    countries: Sequence[str] = ("JP", "US", "KR", "GB"),
    max_items: int = 6,
    approve: bool = False,
    enqueue: bool = True,
    include_ranking_only: bool = True,
) -> Dict[str, object]:
    initialize(settings.database_path)
    rules = load_trend_rules()
    observations, errors = collect_google_trends(countries)
    news_observations, news_errors = collect_product_news(rules)
    observations.extend(news_observations)
    errors.extend(news_errors)
    safe_observations = [item for item in observations if not _blocked_observation(item)]
    client = RakutenProductClient()
    ranking_cache: Dict[str, List[RakutenProduct]] = {}
    ranking_errors: List[str] = []
    genre_ids = sorted({rule.genre_id for rule in rules if rule.genre_id})
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(client.ranking_items, genre_id, "realtime"): genre_id for genre_id in genre_ids}
        for future in as_completed(futures):
            genre_id = futures[future]
            try:
                ranking_cache[genre_id] = future.result()
            except Exception as exc:
                ranking_cache[genre_id] = []
                ranking_errors.append("%s: %s" % (genre_id, exc))

    matched: List[TrendOpportunity] = []
    for observation in safe_observations:
        text = normalize_text("%s %s" % (observation.topic, observation.news_title))
        trigger_text = normalize_text(
            observation.topic if observation.source_name == "Google Trends" else (observation.news_title or observation.topic)
        )
        for rule in rules:
            if observation.rule_hint and observation.rule_hint != rule.rule_id:
                continue
            if _observation_rule_excluded(text, rule.rule_id):
                continue
            triggers = [term for term in rule.trigger_terms if normalize_text(term) in trigger_text]
            if not triggers and not observation.rule_hint:
                continue
            if observation.rule_hint and not triggers:
                triggers = ["商品ニュース一致"]
            product = _best_ranked_product(
                ranking_cache.get(rule.genre_id, []), rule, focus_text=text,
            )
            if product is None:
                product = _fallback_active_product(rule)
            if product is None:
                continue
            traffic_score = min(20, int(math.log10(_traffic_number(observation.approx_traffic) + 1) * 6))
            news_score = 16 if observation.news_title else 0
            score = min(100, 48 + traffic_score + news_score + min(12, len(triggers) * 4))
            person_note = _person_note(observation)
            evidence = "%s。%s。ニュース掲載品と商品候補は同一商品とは限らず、用途が近い販売中商品として掲載" % (
                observation.evidence_text,
                _ranking_label(product, rule),
            )
            fingerprint = stable_hash(observation.fingerprint, rule.rule_id, product.product_id)
            matched.append(
                TrendOpportunity(
                    fingerprint=fingerprint,
                    rule=rule,
                    observation=observation,
                    product=product,
                    score=score,
                    why_trending=evidence,
                    evidence_label=(
                        ("Google Trends" if observation.source_name == "Google Trends" else "Googleニュース")
                        + ("＋楽天リアルタイムランキング" if product.rank else "＋日本で販売中の商品")
                    ),
                    person_note=person_note,
                )
            )

    if include_ranking_only:
        matched_rules = {item.rule.rule_id for item in matched}
        for rule in rules:
            if rule.rule_id in matched_rules:
                continue
            product = _best_ranked_product(ranking_cache.get(rule.genre_id, []), rule)
            if product is None:
                continue
            fingerprint = stable_hash(
                "ranking-only", datetime.now(timezone.utc).date().isoformat(), rule.rule_id, product.product_id,
            )
            matched.append(
                TrendOpportunity(
                    fingerprint=fingerprint,
                    rule=rule,
                    observation=None,
                    product=product,
                    score=max(35, 58 - min(product.rank, 30)),
                    why_trending=_ranking_label(product, rule),
                    evidence_label="楽天リアルタイムランキング",
                    person_note="",
                )
            )

    matched.sort(key=lambda item: (-int(item.observation is not None), -item.score, item.product.rank, item.rule.rule_id))
    selected = _deduplicate_opportunities(matched, max_items)
    stored, social_inserted = _store_and_enqueue(settings, selected, approve=approve, enqueue=enqueue)
    csv_path = settings.output_dir / "trends" / "latest_trend_opportunities.csv"
    recent_rows = _recent_stored_rows(
        settings,
        rules,
        excluded_rules={item.rule.rule_id for item in selected},
        limit=max(0, max_items - len(selected)),
    )
    _write_opportunities_csv(selected, csv_path, extra_rows=recent_rows)
    return {
        "countries": list(countries),
        "observations": len(observations),
        "safe_observations": len(safe_observations),
        "opportunities": len(selected),
        "carried_forward": len(recent_rows),
        "stored": stored,
        "social_inserted": social_inserted,
        "output": str(csv_path),
        "errors": errors + ranking_errors,
        "items": [_opportunity_dict(item) for item in selected],
    }


def enqueue_latest_opportunities(
    settings: Settings,
    approve: bool = True,
    max_items: int = 6,
) -> Dict[str, object]:
    """Create fresh social rows from recently verified evidence without network access."""
    path = settings.output_dir / "trends" / "latest_trend_opportunities.csv"
    if not path.exists():
        raise ValueError("検証済みトレンドCSVがありません")
    rules = {rule.rule_id: rule for rule in load_trend_rules()}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    items: List[TrendOpportunity] = []
    now = datetime.now(timezone.utc)
    for row in rows:
        rule = rules.get(row.get("rule_id", ""))
        if not rule:
            continue
        evidence_text = normalize_text("%s %s" % (row.get("topic", ""), row.get("news_title", "")))
        product_name = normalize_text(row.get("item_name", ""))
        if _observation_rule_excluded(evidence_text, rule.rule_id):
            continue
        focused_terms = [normalize_text(term) for term in rule.product_terms if normalize_text(term) in evidence_text]
        if focused_terms and not any(term in product_name for term in focused_terms):
            continue
        checked = _datetime_or_none(row.get("checked_at", ""))
        if not checked or (now - checked).total_seconds() > 48 * 3600:
            continue
        observation: Optional[TrendObservation] = None
        if row.get("news_title") or row.get("approx_traffic"):
            source_name = "Google Trends" if "Google Trends" in row.get("evidence_label", "") else "Google News"
            observation = TrendObservation(
                fingerprint=stable_hash("cached-observation", row.get("fingerprint", "")),
                source_name=source_name,
                country_code=row.get("country_code") or _country_code_from_name(row.get("country_name", "日本")),
                country_name=row.get("country_name", "日本"),
                topic=row.get("topic", ""),
                approx_traffic=row.get("approx_traffic", ""),
                news_title=row.get("news_title", ""),
                news_url=row.get("news_url", ""),
                news_source=row.get("news_source", ""),
                published_at=row.get("checked_at", ""),
                rule_hint=rule.rule_id,
            )
        product = RakutenProduct(
            product_id=row.get("item_code", ""), name=row.get("item_name", ""),
            min_price=int(float(row.get("price") or 0)), max_price=int(float(row.get("price") or 0)),
            product_url=row.get("item_url", ""), affiliate_url=row.get("affiliate_url", ""),
            image_url=row.get("image_url", ""), review_count=int(float(row.get("review_count") or 0)),
            review_average=float(row.get("review_average") or 0), availability=1,
            rank=int(float(row.get("rank") or 0)), genre_id=rule.genre_id,
        )
        if not product.name or not product.affiliate_url:
            continue
        items.append(TrendOpportunity(
            fingerprint=row.get("fingerprint", "") or stable_hash(rule.rule_id, product.product_id),
            rule=rule, observation=observation, product=product,
            score=int(float(row.get("score") or 0)), why_trending=row.get("why_trending", ""),
            evidence_label=row.get("evidence_label", ""), person_note=_person_note(observation) if observation else "",
        ))
        if len(items) >= max(1, max_items):
            break
    if not items:
        raise ValueError("48時間以内の検証済み候補がありません")
    stored, inserted = _store_and_enqueue(settings, items, approve=approve, enqueue=True)
    return {"source": str(path), "items": len(items), "stored": stored, "social_inserted": inserted}


def _datetime_or_none(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _store_and_enqueue(
    settings: Settings,
    opportunities: Sequence[TrendOpportunity],
    approve: bool,
    enqueue: bool,
) -> Tuple[int, int]:
    stored = 0
    social_inserted = 0
    with transaction(settings.database_path) as conn:
        for item in opportunities:
            observation_id = None
            if item.observation:
                observation_id = _upsert_observation(conn, item.observation)
            rank_id = _upsert_rank(conn, item)
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO trend_opportunities(
                    fingerprint, observation_id, rank_snapshot_id, rule_id, category, page_slug,
                    country_name, topic, entity, audience, why_trending, evidence_label, score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.fingerprint, observation_id, rank_id, item.rule.rule_id, item.rule.category,
                    item.rule.page_slug, item.country_name, item.topic, item.topic, item.rule.audience,
                    item.why_trending, item.evidence_label, item.score,
                ),
            )
            stored += int(cursor.rowcount > 0)
            if enqueue:
                social_inserted += _enqueue_opportunity(conn, settings, item, approve)
    return stored, social_inserted


def _upsert_observation(conn, item: TrendObservation) -> int:
    conn.execute(
        """
        INSERT OR IGNORE INTO trend_observations(
            fingerprint, source_name, country_code, country_name, topic, approx_traffic,
            entity, news_title, news_url, news_source, published_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item.fingerprint, item.source_name, item.country_code, item.country_name, item.topic,
            item.approx_traffic, item.topic, item.news_title, item.news_url, item.news_source,
            item.published_at or None,
        ),
    )
    row = conn.execute("SELECT id FROM trend_observations WHERE fingerprint=?", (item.fingerprint,)).fetchone()
    return int(row["id"])


def _upsert_rank(conn, item: TrendOpportunity) -> int:
    product = item.product
    fingerprint = stable_hash(
        "rakuten-ranking", item.rule.genre_id, product.product_id, str(product.rank),
        datetime.now(timezone.utc).date().isoformat(),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO market_rank_snapshots(
            fingerprint, network, genre_id, genre_name, period, rank, item_code, item_name,
            price, affiliate_url, item_url, image_url, review_count, review_average
        ) VALUES (?, 'rakuten', ?, ?, 'realtime', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fingerprint, item.rule.genre_id, item.rule.genre_name, product.rank,
            product.product_id, product.name, product.min_price, product.affiliate_url,
            product.product_url, product.image_url, product.review_count, product.review_average,
        ),
    )
    row = conn.execute("SELECT id FROM market_rank_snapshots WHERE fingerprint=?", (fingerprint,)).fetchone()
    return int(row["id"])


def _enqueue_opportunity(conn, settings: Settings, item: TrendOpportunity, approve: bool) -> int:
    slug = "trend-%s-%s" % (item.rule.rule_id, item.fingerprint[:12])
    event = conn.execute("SELECT id FROM trend_events WHERE canonical_topic=? ORDER BY id DESC LIMIT 1", (slug,)).fetchone()
    if event is None:
        cursor = conn.execute(
            """
            INSERT INTO trend_events(canonical_topic, title, summary, category, status, score_total, score_json)
            VALUES (?, ?, ?, ?, 'screened', ?, ?)
            """,
            (
                slug, item.topic, item.why_trending, item.rule.category, item.score,
                json.dumps({
                    "country": item.country_name,
                    "trend_scope": item.trend_scope,
                    "market_label": item.market_label,
                    "evidence": item.evidence_label,
                }, ensure_ascii=False),
            ),
        )
        event_id = int(cursor.lastrowid)
    else:
        event_id = int(event["id"])
    content = conn.execute("SELECT id FROM content_items WHERE slug=?", (slug,)).fetchone()
    if content is None:
        cursor = conn.execute(
            """
            INSERT INTO content_items(event_id, content_type, title, slug, file_path, status, generator)
            VALUES (?, 'trend_social', ?, ?, ?, 'draft', 'trend_screening')
            """,
            (event_id, item.topic, slug, "output/trends/latest_trend_opportunities.csv"),
        )
        content_id = int(cursor.lastrowid)
    else:
        content_id = int(content["id"])
    target_url = _target_url(settings, item.rule.page_slug)
    approval = "approved" if approve else "pending"
    inserted = 0
    x_text = _x_post(item)
    fitted_x = _fit_text(x_text, "x", target_url)
    x_fingerprint = stable_hash("trend", "x", item.fingerprint, normalize_text(fitted_x))
    cursor = conn.execute(
        """
        INSERT INTO social_posts(
            content_id, platform, variant_key, post_text, target_url, media_json,
            fingerprint, scheduled_at, status, approval_status
        ) VALUES (?, 'x', 'trend-evidence', ?, ?, '{}', ?, ?, ?, ?)
        ON CONFLICT(content_id, platform, variant_key) DO UPDATE SET
            post_text=excluded.post_text, target_url=excluded.target_url,
            fingerprint=excluded.fingerprint, scheduled_at=excluded.scheduled_at,
            status=excluded.status, approval_status=excluded.approval_status,
            last_error='', updated_at=CURRENT_TIMESTAMP
        WHERE social_posts.status IN ('rejected', 'failed')
        """,
        (
            content_id, fitted_x, target_url, x_fingerprint, _next_schedule(conn, "x"),
            "ready" if approve else "queued", approval,
        ),
    )
    inserted += int(cursor.rowcount > 0)

    instagram_caption = _instagram_caption(item)
    slides = _instagram_slides(item)
    media = json.dumps(
        {"slides": slides, "media_urls": [], "source_image_url": item.product.image_url},
        ensure_ascii=False,
    )
    ig_fingerprint = stable_hash("trend", "instagram", item.fingerprint, normalize_text(instagram_caption))
    cursor = conn.execute(
        """
        INSERT INTO social_posts(
            content_id, platform, variant_key, post_text, target_url, media_json,
            fingerprint, scheduled_at, status, approval_status
        ) VALUES (?, 'instagram', 'trend-carousel', ?, ?, ?, ?, ?, 'media_required', ?)
        ON CONFLICT(content_id, platform, variant_key) DO UPDATE SET
            post_text=excluded.post_text, target_url=excluded.target_url,
            media_json=excluded.media_json, fingerprint=excluded.fingerprint,
            scheduled_at=excluded.scheduled_at, status='media_required',
            approval_status=excluded.approval_status, last_error='',
            updated_at=CURRENT_TIMESTAMP
        WHERE social_posts.status IN ('rejected', 'failed')
        """,
        (
            content_id, _fit_text(instagram_caption, "instagram", target_url), target_url,
            media, ig_fingerprint, _next_schedule(conn, "instagram"), approval,
        ),
    )
    inserted += int(cursor.rowcount > 0)
    return inserted


def _x_post(item: TrendOpportunity) -> str:
    if item.observation:
        source = item.observation.news_source or item.observation.source_name or "関連メディア"
        if item.observation.source_name == "Google Trends":
            lead = "【%s】%s。%sが報道。" % (
                item.market_label, _shorten(item.topic, 18), _shorten(source, 10),
            )
        else:
            lead = "【%s】%sが「%s」を掲載。" % (
                item.market_label, _shorten(source, 10), _shorten(item.topic, 18),
            )
    else:
        lead = "【日本で売れ筋】楽天リアルタイムランキングを確認。"
    product = _shorten(item.product.name, 16)
    product_status = "楽天%s位" % item.product.rank if item.product.rank else "日本で販売中・レビュー確認済み"
    note = " 人物の愛用品を示すものではありません。" if item.person_note else ""
    return "%s 関連候補は%s「%s」。%s%s 他の商品もくらメモへ。" % (
        lead, product_status, product, "掲載品と同一とは限りません。", note,
    )


def _instagram_caption(item: TrendOpportunity) -> str:
    product_status = "楽天リアルタイムランキング%s位" % item.product.rank if item.product.rank else "日本で販売中・レビュー確認済み"
    source = item.observation.news_source if item.observation else "楽天市場"
    details = item.why_trending
    note = "\n\n%s" % item.person_note if item.person_note else ""
    return (
        "【%s】%s\n\n%s\n\n"
        "こんな時に：%s\n"
        "向いている人：%s\n"
        "関連カテゴリの候補：%s「%s」\n"
        "※ニュース掲載品と同一商品とは限りません。\n\n"
        "ほかにも今売れている商品を用途別にまとめています。プロフィールのリンクから確認できます。"
        "%s\n\n情報源：%s"
    ) % (
        item.market_label, item.topic, details, item.rule.context, item.rule.audience,
        product_status, _shorten(item.product.name, 70), note, source,
    )


def _instagram_slides(item: TrendOpportunity) -> List[str]:
    product_status = "楽天リアルタイムランキング%s位" % item.product.rank if item.product.rank else "日本で販売中・レビュー確認済み"
    source = item.observation.news_source if item.observation else "楽天市場"
    return [
        "%s\n%s" % (item.market_label, item.topic),
        "なぜ話題？\n%s" % _shorten(item.why_trending, 95),
        "こんな時に使える\n%s" % item.rule.context,
        "日本で確認できる候補\n%s" % product_status,
        "%s\n%s" % (_shorten(item.product.name, 58), item.rule.audience),
        "選ぶ前に\n価格・レビュー・対応条件を確認",
        "ほかの売れ筋も\nくらメモで用途別に確認\n情報源：%s" % source,
    ]


def _recent_stored_rows(
    settings: Settings,
    rules: Sequence[TrendRule],
    excluded_rules: set[str],
    limit: int,
) -> List[Dict[str, object]]:
    if limit <= 0:
        return []
    rule_map = {rule.rule_id: rule for rule in rules}
    with transaction(settings.database_path) as conn:
        rows = conn.execute(
            """
            SELECT t.*, t.created_at AS checked_at,
                   o.country_code, o.approx_traffic, o.news_title, o.news_url, o.news_source,
                   r.rank, r.genre_name, r.item_code, r.item_name, r.price,
                   r.affiliate_url, r.item_url, r.image_url, r.review_count, r.review_average
            FROM trend_opportunities t
            LEFT JOIN trend_observations o ON o.id=t.observation_id
            LEFT JOIN market_rank_snapshots r ON r.id=t.rank_snapshot_id
            WHERE t.created_at >= datetime('now', '-2 days')
            ORDER BY t.score DESC, t.created_at DESC
            """
        ).fetchall()
    result: List[Dict[str, object]] = []
    used = set(excluded_rules)
    for raw in rows:
        row = dict(raw)
        rule_id = str(row.get("rule_id", ""))
        rule = rule_map.get(rule_id)
        if not rule or rule_id in used or not row.get("item_name"):
            continue
        used.add(rule_id)
        country_code = str(row.get("country_code") or _country_code_from_name(str(row.get("country_name", "日本"))))
        source_name = "Google Trends" if "Google Trends" in str(row.get("evidence_label", "")) else "Google News"
        display_country = COUNTRIES.get(country_code, str(row.get("country_name", "海外")))
        market_label = _market_label(country_code, display_country, source_name)
        why_trending = str(row.get("why_trending", "")).replace("米国", "アメリカ").replace("英国", "イギリス")
        if country_code != "JP" and why_trending and not why_trending.startswith("【"):
            why_trending = "【%s】%s" % (market_label, why_trending)
        result.append({
            "fingerprint": row.get("fingerprint", ""), "rule_id": rule_id,
            "category": row.get("category", ""), "page_slug": row.get("page_slug", ""),
            "country_code": country_code,
            "country_name": display_country, "topic": row.get("topic", ""),
            "trend_scope": "japan_now" if country_code == "JP" else "overseas_watch",
            "market_label": market_label,
            "approx_traffic": row.get("approx_traffic", ""), "news_title": row.get("news_title", ""),
            "news_url": row.get("news_url", ""), "news_source": row.get("news_source", ""),
            "why_trending": why_trending, "evidence_label": row.get("evidence_label", ""),
            "audience": row.get("audience", rule.audience), "context": rule.context,
            "rank": row.get("rank", 0), "genre_name": row.get("genre_name", rule.genre_name),
            "item_code": row.get("item_code", ""), "item_name": row.get("item_name", ""),
            "price": row.get("price", 0), "affiliate_url": row.get("affiliate_url", ""),
            "item_url": row.get("item_url", ""), "image_url": row.get("image_url", ""),
            "review_count": row.get("review_count", 0), "review_average": row.get("review_average", 0),
            "score": row.get("score", 0), "person_note": "",
            "checked_at": row.get("checked_at", ""),
        })
        if len(result) >= limit:
            break
    return result


def _write_opportunities_csv(
    items: Sequence[TrendOpportunity],
    path: Path,
    extra_rows: Sequence[Dict[str, object]] = (),
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "fingerprint", "rule_id", "category", "page_slug", "country_code", "country_name", "trend_scope", "market_label", "topic",
        "approx_traffic", "news_title", "news_url", "news_source", "why_trending",
        "evidence_label", "audience", "context", "rank", "genre_name", "item_code",
        "item_name", "price", "affiliate_url", "item_url", "image_url", "review_count",
        "review_average", "score", "person_note", "checked_at",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in items:
            writer.writerow(_opportunity_dict(item))
        for row in extra_rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _opportunity_dict(item: TrendOpportunity) -> Dict[str, object]:
    observation = item.observation
    return {
        "fingerprint": item.fingerprint,
        "rule_id": item.rule.rule_id,
        "category": item.rule.category,
        "page_slug": item.rule.page_slug,
        "country_code": observation.country_code if observation else "JP",
        "country_name": item.country_name,
        "trend_scope": item.trend_scope,
        "market_label": item.market_label,
        "topic": item.topic,
        "approx_traffic": observation.approx_traffic if observation else "",
        "news_title": observation.news_title if observation else "",
        "news_url": observation.news_url if observation else "",
        "news_source": observation.news_source if observation else "",
        "why_trending": item.why_trending,
        "evidence_label": item.evidence_label,
        "audience": item.rule.audience,
        "context": item.rule.context,
        "rank": item.product.rank,
        "genre_name": item.rule.genre_name,
        "item_code": item.product.product_id,
        "item_name": item.product.name,
        "price": item.product.min_price,
        "affiliate_url": item.product.affiliate_url,
        "item_url": item.product.product_url,
        "image_url": item.product.image_url,
        "review_count": item.product.review_count,
        "review_average": item.product.review_average,
        "score": item.score,
        "person_note": item.person_note,
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def _best_ranked_product(
    products: Iterable[RakutenProduct],
    rule: TrendRule,
    focus_text: str = "",
) -> Optional[RakutenProduct]:
    candidates: List[Tuple[int, RakutenProduct]] = []
    terms = [normalize_text(term) for term in rule.product_terms]
    focused_terms = [term for term in terms if term and term in focus_text]
    for product in products:
        name = normalize_text(product.name)
        if _ranking_product_excluded(name, rule.rule_id):
            continue
        hits = sum(1 for term in terms if term and term in name)
        if focused_terms and not any(term in name for term in focused_terms):
            continue
        if not hits or not product.affiliate_url or not product.image_url or not product.min_price:
            continue
        if product.review_count and product.review_count < 8:
            continue
        if product.review_average and product.review_average < 4.0:
            continue
        quality = hits * 20 + max(0, 35 - product.rank)
        quality += min(15, int(math.log10(product.review_count + 1) * 5))
        candidates.append((quality, product))
    candidates.sort(key=lambda item: (-item[0], item[1].rank, -item[1].review_count))
    return candidates[0][1] if candidates else None


def _fallback_active_product(rule: TrendRule) -> Optional[RakutenProduct]:
    """Use an already quality-gated Japanese offer when ranking API is unavailable."""
    map_path = ROOT / "data" / "comparison_product_map.csv"
    offers_path = ROOT / "data" / "offers.csv"
    assets_path = ROOT / "data" / "offer_assets.csv"
    if not map_path.exists() or not offers_path.exists() or not assets_path.exists():
        return None
    with map_path.open(encoding="utf-8-sig", newline="") as handle:
        offer_ids = [
            row.get("offer_candidate_id", "") for row in csv.DictReader(handle)
            if row.get("page_slug") == rule.page_slug
        ]
    with offers_path.open(encoding="utf-8-sig", newline="") as handle:
        offers = {row.get("offer_id", ""): row for row in csv.DictReader(handle)}
    with assets_path.open(encoding="utf-8-sig", newline="") as handle:
        assets = {row.get("offer_id", ""): row for row in csv.DictReader(handle)}
    for offer_id in offer_ids:
        offer = offers.get(offer_id, {})
        asset = assets.get(offer_id, {})
        review_count = int(float(asset.get("review_count") or 0))
        review_average = float(asset.get("review_average") or 0)
        if (
            offer.get("status") != "active" or not offer.get("affiliate_url")
            or not asset.get("image_url") or review_count < 20 or review_average < 4.0
        ):
            continue
        price = int(float(asset.get("min_price") or 0))
        return RakutenProduct(
            product_id=offer_id,
            name=offer.get("name", offer_id),
            min_price=price,
            max_price=price,
            product_url=offer.get("landing_url", ""),
            affiliate_url=offer.get("affiliate_url", ""),
            image_url=asset.get("image_url", ""),
            review_count=review_count,
            review_average=review_average,
            availability=1,
            rank=0,
            genre_id=rule.genre_id,
        )
    return None


def _ranking_product_excluded(name: str, rule_id: str) -> bool:
    exclusions = {
        "heat": ["除湿", "衣類乾燥", "布団乾燥", "ヒーター", "暖房"],
        "pc": ["ノートパソコン", "ノートpc", "デスクトップ", "中古パソコン", "ゲーミングpc"],
        "beauty": ["口紅", "リップモンスター", "アイシャドウ", "ファンデーション", "マスカラ"],
        "fitness": ["ウェア", "シューズ", "ゴルフ", "水着"],
        "travel": ["ゴルフ", "キャンプテント", "釣り"],
    }
    return any(term in name for term in exclusions.get(rule_id, []))


def _observation_rule_excluded(text: str, rule_id: str) -> bool:
    exclusions = {
        "wellness": ["プロテイン", "protein", "クレアチン", "creatine", "eaa", "bcaa"],
        "housework": ["布団乾燥機"] if "衣類乾燥" in text and "布団乾燥機" not in text else [],
        "heat": ["暖房", "ヒーター"],
    }
    return any(term in text for term in exclusions.get(rule_id, []))


def _deduplicate_opportunities(items: Sequence[TrendOpportunity], limit: int) -> List[TrendOpportunity]:
    result: List[TrendOpportunity] = []
    used_products = set()
    used_rules = set()

    def add(item: TrendOpportunity) -> bool:
        product_key = item.product.product_id or item.product.affiliate_url
        if product_key in used_products or item.rule.rule_id in used_rules:
            return False
        used_products.add(product_key)
        used_rules.add(item.rule.rule_id)
        result.append(item)
        return True

    # 海外の検索トレンドと日本の現在を別レーンで最低1件ずつ確保する。
    for wanted in ("overseas_watch", "japan_now"):
        for item in items:
            if item.trend_scope == wanted and add(item):
                break
        if len(result) >= max(1, limit):
            return result
    for item in items:
        add(item)
        if len(result) >= max(1, limit):
            break
    return result


def _market_label(country_code: str, country_name: str, source_name: str = "") -> str:
    country = country_name or COUNTRIES.get(country_code, "海外")
    if source_name == "Google Trends":
        return "%sで検索急上昇" % country
    if source_name == "Google News":
        return "%sのニュースで注目" % country
    if country_code == "JP" or country == "日本":
        return "日本で注目"
    return "%sで注目" % country


def _country_code_from_name(country_name: str) -> str:
    aliases = {"米国": "US", "アメリカ": "US", "韓国": "KR", "英国": "GB", "イギリス": "GB", "日本": "JP"}
    return aliases.get(country_name, "OTHER")


def _ranking_label(product: RakutenProduct, rule: TrendRule) -> str:
    if not product.rank:
        return "日本で販売中・レビュー確認済みの関連候補"
    return "楽天市場「%s」リアルタイムランキング%s位の候補" % (rule.genre_name, product.rank)


def _blocked_observation(item: TrendObservation) -> bool:
    text = "%s %s" % (item.topic, item.news_title)
    return any(term in text for term in BLOCKED_NEWS_TERMS)


def _person_note(item: TrendObservation) -> str:
    person_context = "氏|選手|俳優|女優|歌手|タレント|代表|結婚|発表"
    named_person = re.search(r"[一-龥々]{2,5}[一-龥々]{2,5}(?:さん|氏|選手|、|，)", item.news_title)
    if named_person or (re.fullmatch(r"[一-龥々]{2,6}", item.topic) and re.search(person_context, item.news_title)):
        return "話題の人物がこの商品を使用しているという意味ではありません。"
    return ""


def _target_url(settings: Settings, page_slug: str) -> str:
    if settings.site_base_url:
        return "%s/%s.html#trend-evidence" % (settings.site_base_url, page_slug)
    return "http://127.0.0.1:8080/%s/#trend-evidence" % page_slug


def _traffic_number(value: str) -> int:
    digits = re.sub(r"[^0-9]", "", value or "")
    return int(digits or 0)


def _parse_date(value: str) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except (TypeError, ValueError):
        return value


def _xml_text(element: Optional[ET.Element]) -> str:
    return "" if element is None else "".join(element.itertext()).strip()


def _split_pipe(value: str) -> List[str]:
    return [item.strip() for item in (value or "").split("|") if item.strip()]


def _shorten(value: str, limit: int) -> str:
    clean = " ".join((value or "").split())
    return clean if len(clean) <= limit else clean[: max(1, limit - 1)].rstrip() + "…"
