from __future__ import annotations

import csv
import glob
import math
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Dict, List

from .catalog import import_offers
from .database import transaction
from .product_scout import ProductCandidate, _product_group_mismatch_penalty, _upsert_offer_asset_csv
from .settings import ROOT, Settings
from .catalog import upsert_offer_csv


PAGE_ALIASES = {
    "hair-grooming-items-comparison": "mens-grooming-items-comparison",
}


def _candidate_from_row(row: Dict[str, str], page_slug: str) -> ProductCandidate:
    return ProductCandidate(
        page_slug=page_slug,
        offer_id=row.get("offer_id", ""),
        product_group=row.get("product_group", "商品候補"),
        keyword=row.get("keyword", ""),
        category=row.get("category", ""),
        name=row.get("name", ""),
        score=int(float(row.get("score") or 0)),
        min_price=int(float(row.get("min_price") or 0)),
        max_price=int(float(row.get("max_price") or 0)),
        review_count=int(float(row.get("review_count") or 0)),
        review_average=float(row.get("review_average") or 0),
        product_url=row.get("product_url", ""),
        affiliate_url=row.get("affiliate_url", ""),
        image_url=row.get("image_url", ""),
        shop_name=row.get("shop_name", ""),
        reasons=[reason for reason in row.get("reasons", "").split("|") if reason],
    )


def _quality(candidate: ProductCandidate) -> float:
    return candidate.score + candidate.review_average * 5 + min(20, math.log10(candidate.review_count + 1) * 5)


def _eligible(candidate: ProductCandidate) -> bool:
    return bool(
        candidate.name
        and candidate.affiliate_url
        and candidate.image_url
        and candidate.score >= 75
        and candidate.review_count >= 20
        and candidate.review_average >= 4.0
        and _product_group_mismatch_penalty(candidate.name, candidate.product_group) == 0
        and "商品タイプ不一致の可能性" not in candidate.reasons
    )


def _load_cached_candidates() -> List[ProductCandidate]:
    result: List[ProductCandidate] = []
    for filename in sorted(glob.glob(str(ROOT / "output" / "products" / "*.csv"))):
        with Path(filename).open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                page_slug = row.get("page_slug", "")
                candidate = _candidate_from_row(row, page_slug)
                if _eligible(candidate):
                    result.append(candidate)
    return result


def product_page_counts(target_per_page: int = 8) -> List[Dict[str, object]]:
    with (ROOT / "data" / "comparison_product_map.csv").open(encoding="utf-8-sig", newline="") as handle:
        map_rows = list(csv.DictReader(handle))
    with (ROOT / "data" / "offers.csv").open(encoding="utf-8-sig", newline="") as handle:
        active = {
            row["offer_id"] for row in csv.DictReader(handle)
            if row.get("status") == "active" and row.get("affiliate_url")
        }
    result: List[Dict[str, object]] = []
    for page_slug in sorted({row["page_slug"] for row in map_rows}):
        rows = [row for row in map_rows if row["page_slug"] == page_slug]
        count = sum(row["offer_candidate_id"] in active for row in rows)
        result.append({
            "page_slug": page_slug,
            "page_title": rows[0].get("page_title", page_slug),
            "active_products": count,
            "target": target_per_page,
            "gap": max(0, target_per_page - count),
        })
    return result


def _normalize_promoted_slot_ids(map_rows: List[Dict[str, str]], settings: Settings) -> int:
    promoted = [row for row in map_rows if row.get("notes") == "検証済み楽天APIキャッシュから追加候補を採用"]
    counters: Dict[str, int] = {}
    renames: Dict[str, str] = {}
    for row in promoted:
        page_slug = row["page_slug"]
        counters[page_slug] = counters.get(page_slug, 0) + 1
        prefix = page_slug.replace("-comparison", "").replace("-items", "").replace("-", "_")
        new_id = "%s_alt_%02d" % (prefix, counters[page_slug])
        old_id = row["offer_candidate_id"]
        row["offer_candidate_id"] = new_id
        if old_id != new_id:
            renames[old_id] = new_id
    if not renames:
        return 0

    for filename in (ROOT / "data" / "offers.csv", ROOT / "data" / "offer_assets.csv"):
        with filename.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            fields = list(reader.fieldnames or [])
        for row in rows:
            if row.get("offer_id") in renames:
                row["offer_id"] = renames[row["offer_id"]]
        with filename.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    with transaction(settings.database_path) as conn:
        conn.executemany("UPDATE offers SET status='paused' WHERE offer_id=?", [(old_id,) for old_id in renames])
    return len(renames)


def expand_products_from_cache(settings: Settings, target_per_page: int = 8, refresh: bool = False) -> Dict[str, object]:
    """Fill empty product slots from previously verified Rakuten API snapshots.

    It never invents products or affiliate URLs. Only candidates that already passed
    the review/rating/type gates are promoted, and existing active slots are kept.
    """
    map_path = ROOT / "data" / "comparison_product_map.csv"
    offers_path = ROOT / "data" / "offers.csv"
    with map_path.open(encoding="utf-8-sig", newline="") as handle:
        map_rows = list(csv.DictReader(handle))
    map_fields = [
        "page_slug", "page_title", "category", "offer_candidate_id", "product_group", "priority",
        "search_keywords", "reader_problem", "comparison_points", "affiliate_priority", "status", "notes",
    ]
    with offers_path.open(encoding="utf-8-sig", newline="") as handle:
        offer_rows = list(csv.DictReader(handle))
    offer_fields = [
        "offer_id", "network", "name", "category", "keywords", "problem_tags", "event_tags",
        "affiliate_url", "landing_url", "reward_type", "reward_value", "allowed_media", "status", "last_verified_at",
    ]
    promoted_ids = {
        row["offer_candidate_id"] for row in map_rows
        if row.get("notes") == "検証済み楽天APIキャッシュから追加候補を採用"
    }
    if refresh and promoted_ids:
        offer_rows = [row for row in offer_rows if row.get("offer_id") not in promoted_ids]
        with offers_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=offer_fields)
            writer.writeheader()
            writer.writerows(offer_rows)
        asset_path = ROOT / "data" / "offer_assets.csv"
        with asset_path.open(encoding="utf-8-sig", newline="") as handle:
            assets = list(csv.DictReader(handle))
        asset_fields = ["offer_id", "image_url", "shop_name", "min_price", "review_count", "review_average", "score", "updated_at"]
        assets = [row for row in assets if row.get("offer_id") not in promoted_ids]
        with asset_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=asset_fields)
            writer.writeheader()
            writer.writerows(assets)
        with transaction(settings.database_path) as conn:
            conn.executemany("UPDATE offers SET status='paused' WHERE offer_id=?", [(offer_id,) for offer_id in promoted_ids])
    active = {
        row["offer_id"]: row for row in offer_rows
        if row.get("status") == "active" and row.get("affiliate_url")
    }
    active_urls = {row.get("landing_url") or row.get("affiliate_url") for row in active.values()}
    cached = _load_cached_candidates()
    expanded: Dict[str, int] = {}

    pages = sorted({row["page_slug"] for row in map_rows})
    for page_slug in pages:
        if page_slug in {"ai-tools-comparison", "trend-cosmetics-comparison"}:
            continue
        page_rows = [row for row in map_rows if row["page_slug"] == page_slug]
        active_count = sum(row["offer_candidate_id"] in active for row in page_rows)
        missing = max(0, target_per_page - active_count)
        if not missing:
            continue
        empty_slots = [row for row in page_rows if row["offer_candidate_id"] not in active]
        source_slug = PAGE_ALIASES.get(page_slug, page_slug)
        pool = [candidate for candidate in cached if candidate.page_slug == source_slug]
        pool.sort(key=lambda item: (-_quality(item), item.min_price or 999999, item.name))
        selected: List[ProductCandidate] = []
        seen = set(active_urls)
        group_counts: Dict[str, int] = {}
        for row in page_rows:
            if row["offer_candidate_id"] in active:
                group = row.get("product_group", "")
                group_counts[group] = group_counts.get(group, 0) + 1
        allowed_groups = set(group_counts)
        for candidate in pool:
            key = candidate.product_url or candidate.affiliate_url
            if not key or key in seen:
                continue
            if candidate.product_group not in allowed_groups:
                continue
            if group_counts.get(candidate.product_group, 0) >= 2:
                continue
            seen.add(key)
            selected.append(candidate)
            group_counts[candidate.product_group] = group_counts.get(candidate.product_group, 0) + 1
            if len(selected) >= min(missing, len(empty_slots)):
                break
        for slot, candidate in zip(empty_slots, selected):
            source_row = next(
                (row for row in page_rows if row.get("product_group") == candidate.product_group),
                None,
            )
            if source_row:
                for field in ("product_group", "search_keywords", "reader_problem", "comparison_points"):
                    slot[field] = source_row.get(field, slot.get(field, ""))
            else:
                slot["product_group"] = candidate.product_group or slot["product_group"]
            slot["notes"] = "検証済み楽天APIキャッシュから追加候補を採用"
            promoted = replace(candidate, offer_id=slot["offer_candidate_id"], page_slug=page_slug, category=slot["category"])
            upsert_offer_csv({
                "offer_id": promoted.offer_id,
                "network": "rakuten",
                "name": promoted.name,
                "category": promoted.category,
                "keywords": "%s|%s|%s" % (promoted.product_group, promoted.keyword, promoted.name),
                "problem_tags": promoted.product_group,
                "event_tags": promoted.keyword,
                "affiliate_url": promoted.affiliate_url,
                "landing_url": promoted.product_url,
                "reward_type": "percent",
                "reward_value": "0",
                "allowed_media": "site|x|instagram",
                "status": "active",
                "last_verified_at": date.today().isoformat(),
            })
            _upsert_offer_asset_csv(promoted)
            active[promoted.offer_id] = {"landing_url": promoted.product_url, "affiliate_url": promoted.affiliate_url}
            active_urls.add(promoted.product_url or promoted.affiliate_url)
        if selected:
            expanded[page_slug] = len(selected)

    normalized_ids = _normalize_promoted_slot_ids(map_rows, settings)
    with map_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=map_fields)
        writer.writeheader()
        writer.writerows(map_rows)
    import_offers(settings)
    return {
        "expanded": expanded, "added": sum(expanded.values()), "target_per_page": target_per_page,
        "refreshed": refresh, "normalized_ids": normalized_ids,
        "page_counts": product_page_counts(target_per_page),
    }
