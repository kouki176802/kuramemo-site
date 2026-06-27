from __future__ import annotations

import csv
import json
import math
import threading
import time
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .catalog import list_offers
from .database import connect, initialize, transaction
from .models import Offer
from .product_scout import ProductCandidate, activate_candidates, scout_page_products, score_rakuten_product
from .rakuten import RakutenProductClient
from .settings import ROOT, Settings
from .static_site import build_static_site


MIN_REVIEW_COUNT = 20
MIN_REVIEW_AVERAGE = 4.0
MIN_CANDIDATE_SCORE = 75
ROTATION_COOLDOWN_DAYS = 12
REPLACEMENT_MARGIN = 6.0


def run_product_operations(
    settings: Settings,
    mode: str = "daily",
    apply_changes: bool = True,
    build_site: bool = True,
    client: Optional[RakutenProductClient] = None,
    delay_seconds: float = 1.1,
    max_slots: int = 0,
) -> Dict[str, object]:
    if mode not in {"daily", "rotation"}:
        raise ValueError("modeはdailyまたはrotationを指定してください")
    initialize(settings.database_path)
    client = client or RakutenProductClient()
    offers = {offer.offer_id: offer for offer in list_offers(settings)}
    rows = _load_map_rows()
    rows = [row for row in rows if row["offer_candidate_id"] in offers and offers[row["offer_candidate_id"]].status == "active"]
    if max_slots > 0:
        rows = rows[:max_slots]
    row_by_offer = {row["offer_candidate_id"]: row for row in rows}
    assets = _load_assets()
    run_id = _start_run(settings, mode)
    decisions: List[Dict[str, object]] = []
    try:
        _initialize_slot_state(settings, offers, assets)
        if mode == "daily":
            decisions = _daily_audit(settings, client, row_by_offer, offers, assets, apply_changes, delay_seconds)
        else:
            decisions = _rotation_audit(settings, client, rows, offers, assets, apply_changes, delay_seconds)
        _save_decisions(settings, run_id, decisions)
        changed = sum(1 for item in decisions if str(item["decision"]).startswith("replaced"))
        refreshed = sum(1 for item in decisions if item["decision"] == "refreshed")
        site_result = None
        if apply_changes and build_site and (changed or refreshed):
            site_result = build_static_site(settings, settings.output_dir / "site")
        report_path = _write_report(settings, run_id, mode, decisions)
        summary = _finish_run(settings, run_id, decisions, report_path)
        summary.update({"run_id": run_id, "mode": mode, "report_path": str(report_path), "site": site_result})
        return summary
    except BaseException as exc:
        with transaction(settings.database_path) as conn:
            conn.execute(
                "UPDATE product_operation_runs SET status='failed', finished_at=CURRENT_TIMESTAMP, error=? WHERE id=?",
                (str(exc)[:1000], run_id),
            )
        raise


def _daily_audit(
    settings: Settings,
    client: RakutenProductClient,
    rows: Dict[str, Dict[str, str]],
    offers: Dict[str, Offer],
    assets: Dict[str, Dict[str, str]],
    apply_changes: bool,
    delay_seconds: float,
) -> List[Dict[str, object]]:
    decisions: List[Dict[str, object]] = []
    lookup_results: Dict[str, tuple[str, object]] = {}
    active_rows = [
        (offer_id, row, offers.get(offer_id))
        for offer_id, row in rows.items()
        if offers.get(offer_id) and offers[offer_id].status == "active"
    ]
    rate_lock = threading.Lock()
    last_request_started = [0.0]

    def rate_limited_lookup(offer: Offer, row: Dict[str, str]):
        with rate_lock:
            elapsed = time.monotonic() - last_request_started[0]
            wait_seconds = max(0.0, 1.05 - elapsed)
            if wait_seconds:
                time.sleep(wait_seconds)
            last_request_started[0] = time.monotonic()
        return _lookup_safely(client, offer.landing_url or offer.affiliate_url, row["product_group"])

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(rate_limited_lookup, offer, row): offer_id
            for offer_id, row, offer in active_rows
        }
        for future in as_completed(futures):
            offer_id = futures[future]
            try:
                lookup_results[offer_id] = future.result()
            except Exception:
                lookup_results[offer_id] = ("error", None)
    for offer_id, row in rows.items():
        offer = offers.get(offer_id)
        if not offer or offer.status != "active":
            continue
        current_url = offer.landing_url or offer.affiliate_url
        lookup_status, product = lookup_results.get(offer_id, ("error", None))
        state = _slot_state(settings, offer_id)
        if lookup_status == "ok" and product is not None:
            score, reasons = score_rakuten_product(product, row.get("search_keywords", "").split("|")[0], row["product_group"])
            candidate = _candidate_from_product(row, product, score, reasons)
            if apply_changes:
                activate_candidates(settings, [candidate])
            _update_slot(settings, offer_id, candidate.product_url, "refreshed", _selection_index(candidate), failures=0, reset_activation=False)
            decisions.append(_decision(row, offer, candidate, "refreshed", assets, ["販売中を確認", "価格・評価を更新"]))
            continue

        if lookup_status == "error":
            failures = int(state.get("consecutive_failures", 0))
            _update_slot(settings, offer_id, current_url, "api_error", 0, failures=failures, reset_activation=False)
            decisions.append(_decision(row, offer, None, "api_error", assets, ["楽天APIの一時エラー", "商品状態は変更せず次回再確認"]))
            continue

        failures = int(state.get("consecutive_failures", 0)) + 1
        if failures < 2:
            _update_slot(settings, offer_id, current_url, "watch", 0, failures=failures, reset_activation=False)
            decisions.append(_decision(row, offer, None, "watch", assets, ["販売確認に1回失敗", "次回再確認まで据え置き"]))
            continue

        candidates = scout_page_products(
            settings, row["page_slug"], limit_per_keyword=8, queries_per_group=1,
            delay_seconds=delay_seconds, live_items=True, client=client,
        )
        candidates = [item for item in candidates if item.offer_id == offer_id and _eligible(item)]
        challenger = max(candidates, key=_selection_index) if candidates else None
        if challenger and apply_changes:
            activate_candidates(settings, [challenger])
        decision_name = ("replaced_unavailable" if apply_changes else "recommended_replace_unavailable") if challenger else "issue_no_replacement"
        if challenger and apply_changes:
            _update_slot(settings, offer_id, challenger.product_url, decision_name, _selection_index(challenger), failures=0, reset_activation=True)
        else:
            _update_slot(settings, offer_id, current_url, decision_name, 0, failures=failures, reset_activation=False)
        decisions.append(_decision(row, offer, challenger, decision_name, assets, ["販売確認に連続2回失敗"]))
    return decisions


def _rotation_audit(
    settings: Settings,
    client: RakutenProductClient,
    rows: List[Dict[str, str]],
    offers: Dict[str, Offer],
    assets: Dict[str, Dict[str, str]],
    apply_changes: bool,
    delay_seconds: float,
) -> List[Dict[str, object]]:
    candidates: List[ProductCandidate] = []
    for page_slug in sorted({row["page_slug"] for row in rows}):
        candidates.extend(scout_page_products(
            settings, page_slug, limit_per_keyword=10, queries_per_group=1,
            delay_seconds=delay_seconds, live_items=True, client=client,
        ))
    by_offer: Dict[str, List[ProductCandidate]] = {}
    for candidate in candidates:
        if _eligible(candidate):
            by_offer.setdefault(candidate.offer_id, []).append(candidate)

    decisions: List[Dict[str, object]] = []
    for row in rows:
        offer_id = row["offer_candidate_id"]
        offer = offers.get(offer_id)
        if not offer or offer.status != "active":
            continue
        eligible = by_offer.get(offer_id, [])
        challenger = max(eligible, key=_selection_index) if eligible else None
        performance_bonus, performance_reason = _performance_bonus(settings, offer_id)
        current_index = _current_index(assets.get(offer_id, {})) + performance_bonus
        challenger_index = _selection_index(challenger) if challenger else 0.0
        state = _slot_state(settings, offer_id)
        age_days = _age_days(str(state.get("activated_at", "")))
        current_bad = _current_is_weak(assets.get(offer_id, {}))
        same_product = bool(challenger and _same_product_url(offer.landing_url or offer.affiliate_url, challenger.product_url))
        should_replace = bool(
            challenger and not same_product and (
                current_bad or (age_days >= ROTATION_COOLDOWN_DAYS and challenger_index >= current_index + REPLACEMENT_MARGIN)
            )
        )
        if should_replace:
            if apply_changes:
                activate_candidates(settings, [challenger])
            decision_name = "replaced_better" if apply_changes else "recommended_replace_better"
            if apply_changes:
                _update_slot(settings, offer_id, challenger.product_url, decision_name, challenger_index, failures=0, reset_activation=True)
            else:
                _update_slot(settings, offer_id, offer.landing_url or offer.affiliate_url, decision_name, current_index, failures=0, reset_activation=False)
            reasons = ["品質基準を通過", "現商品より総合指数が高い"]
        else:
            decision_name = "kept"
            reasons = []
            if challenger is None:
                reasons.append("基準を満たす新候補なし")
            elif same_product:
                reasons.append("現商品が引き続き最良候補")
            elif age_days < ROTATION_COOLDOWN_DAYS and not current_bad:
                reasons.append("最低掲載期間内のため維持")
            else:
                reasons.append("改善幅が入替基準未満")
            _update_slot(settings, offer_id, offer.landing_url or offer.affiliate_url, "kept", current_index, failures=0, reset_activation=False)
        if performance_reason:
            reasons.append(performance_reason)
        decisions.append(_decision(row, offer, challenger, decision_name, assets, reasons))
    return decisions


def _eligible(candidate: ProductCandidate) -> bool:
    return bool(
        candidate.affiliate_url
        and candidate.score >= MIN_CANDIDATE_SCORE
        and candidate.review_count >= MIN_REVIEW_COUNT
        and candidate.review_average >= MIN_REVIEW_AVERAGE
        and "商品タイプ不一致の可能性" not in candidate.reasons
    )


def _selection_index(candidate: Optional[ProductCandidate]) -> float:
    if candidate is None:
        return 0.0
    return round(candidate.score + min(25.0, math.log10(candidate.review_count + 1) * 6) + candidate.review_average * 5, 2)


def _current_index(asset: Dict[str, str]) -> float:
    score = float(asset.get("score") or 0)
    reviews = int(float(asset.get("review_count") or 0))
    average = float(asset.get("review_average") or 0)
    return round(score + min(25.0, math.log10(reviews + 1) * 6) + average * 5, 2)


def _current_is_weak(asset: Dict[str, str]) -> bool:
    return int(float(asset.get("review_count") or 0)) < MIN_REVIEW_COUNT or float(asset.get("review_average") or 0) < 3.8


def _performance_bonus(settings: Settings, offer_id: str) -> tuple[float, str]:
    with connect(settings.database_path) as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS conversions, COALESCE(SUM(amount), 0) AS revenue
            FROM conversions WHERE offer_id=? AND status IN ('approved','confirmed')""",
            (offer_id,),
        ).fetchone()
    conversions = int(row["conversions"] or 0)
    revenue = float(row["revenue"] or 0)
    if not conversions and not revenue:
        return 0.0, ""
    bonus = min(20.0, conversions * 4.0 + math.log10(revenue + 1) * 2.0)
    return round(bonus, 2), "承認成果%s件・売上¥%sを維持判断へ反映" % (conversions, f"{revenue:,.0f}")


def _candidate_from_product(row: Dict[str, str], product, score: int, reasons: List[str]) -> ProductCandidate:
    return ProductCandidate(
        page_slug=row["page_slug"], offer_id=row["offer_candidate_id"], product_group=row["product_group"],
        keyword=row.get("search_keywords", "").split("|")[0], category=row["category"], name=product.name,
        score=score, min_price=product.min_price, max_price=product.max_price,
        review_count=product.review_count, review_average=product.review_average,
        product_url=product.product_url, affiliate_url=product.affiliate_url,
        image_url=product.image_url, shop_name=product.shop_name, reasons=reasons,
    )


def _lookup_safely(client: RakutenProductClient, current_url: str, keyword: str):
    item_code = _rakuten_item_code(current_url)
    shop_code = _rakuten_shop_code(current_url)
    if not shop_code:
        return "error", None
    try:
        if item_code and item_code.split(":", 1)[1].isdigit():
            try:
                products = client.lookup_item(item_code)
                product = products[0] if products else None
                return ("ok", product) if product and product.availability == 1 else ("not_found", None)
            except urllib.error.HTTPError as error:
                if error.code not in {400, 404}:
                    return "error", None
        products = client.search_shop_items(shop_code, keyword, limit=30)
        for product in products:
            if _same_product_url(current_url, product.product_url):
                return ("ok", product) if product.availability == 1 else ("not_found", None)
        return "not_found", None
    except urllib.error.HTTPError as error:
        return ("not_found", None) if error.code == 404 else ("error", None)
    except (urllib.error.URLError, TimeoutError):
        return "error", None


def _rakuten_item_code(url: str) -> str:
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.endswith("hb.afl.rakuten.co.jp"):
        query = urllib.parse.parse_qs(parsed.query)
        mobile_target = query.get("m", [""])[0]
        mobile = urllib.parse.urlparse(mobile_target)
        mobile_parts = [part for part in mobile.path.split("/") if part]
        if len(mobile_parts) >= 3 and mobile_parts[1] == "i" and mobile_parts[2].isdigit():
            return "%s:%s" % (mobile_parts[0], mobile_parts[2])
        target = query.get("pc", [""])[0]
        parsed = urllib.parse.urlparse(target)
    if parsed.netloc != "item.rakuten.co.jp":
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    return "%s:%s" % (parts[0], parts[1]) if len(parts) >= 2 else ""


def _rakuten_shop_code(url: str) -> str:
    code = _rakuten_item_code(url)
    return code.split(":", 1)[0] if ":" in code else ""


def _same_product_url(left: str, right: str) -> bool:
    left_code, right_code = _rakuten_item_code(left), _rakuten_item_code(right)
    return bool(left_code and right_code and left_code == right_code) or left == right


def _load_map_rows() -> List[Dict[str, str]]:
    with (ROOT / "data" / "comparison_product_map.csv").open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_assets() -> Dict[str, Dict[str, str]]:
    path = ROOT / "data" / "offer_assets.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["offer_id"]: row for row in csv.DictReader(handle)}


def _initialize_slot_state(settings: Settings, offers: Dict[str, Offer], assets: Dict[str, Dict[str, str]]) -> None:
    with transaction(settings.database_path) as conn:
        for offer_id, offer in offers.items():
            if offer.status != "active":
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO product_slot_state(offer_id, current_product_url, activated_at, last_score)
                VALUES (?, ?, ?, ?)
                """,
                (offer_id, offer.landing_url or offer.affiliate_url, offer.last_verified_at or date.today().isoformat(), _current_index(assets.get(offer_id, {}))),
            )


def _slot_state(settings: Settings, offer_id: str) -> Dict[str, object]:
    with connect(settings.database_path) as conn:
        row = conn.execute("SELECT * FROM product_slot_state WHERE offer_id=?", (offer_id,)).fetchone()
        return dict(row) if row else {}


def _update_slot(settings: Settings, offer_id: str, url: str, decision: str, score: float, failures: int, reset_activation: bool) -> None:
    with transaction(settings.database_path) as conn:
        if reset_activation:
            conn.execute(
                """UPDATE product_slot_state SET current_product_url=?, activated_at=CURRENT_TIMESTAMP,
                last_checked_at=CURRENT_TIMESTAMP, consecutive_failures=?, last_decision=?, last_score=? WHERE offer_id=?""",
                (url, failures, decision, score, offer_id),
            )
        else:
            conn.execute(
                """UPDATE product_slot_state SET current_product_url=?, last_checked_at=CURRENT_TIMESTAMP,
                consecutive_failures=?, last_decision=?, last_score=? WHERE offer_id=?""",
                (url, failures, decision, score, offer_id),
            )


def _start_run(settings: Settings, mode: str) -> int:
    with transaction(settings.database_path) as conn:
        cursor = conn.execute("INSERT INTO product_operation_runs(mode,status) VALUES (?,'running')", (mode,))
        return int(cursor.lastrowid)


def _decision(row, offer, candidate, decision, assets, reasons) -> Dict[str, object]:
    return {
        "offer_id": row["offer_candidate_id"], "page_slug": row["page_slug"], "product_group": row["product_group"],
        "decision": decision, "current_name": offer.name, "candidate_name": candidate.name if candidate else "",
        "current_url": offer.landing_url or offer.affiliate_url, "candidate_url": candidate.product_url if candidate else "",
        "current_score": _current_index(assets.get(row["offer_candidate_id"], {})),
        "candidate_score": _selection_index(candidate), "reasons": reasons + (candidate.reasons if candidate else []),
    }


def _save_decisions(settings: Settings, run_id: int, decisions: Iterable[Dict[str, object]]) -> None:
    with transaction(settings.database_path) as conn:
        for item in decisions:
            conn.execute(
                """INSERT INTO product_decisions(run_id,offer_id,page_slug,decision,current_url,candidate_url,current_score,candidate_score,reasons)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (run_id, item["offer_id"], item["page_slug"], item["decision"], item["current_url"], item["candidate_url"], item["current_score"], item["candidate_score"], json.dumps(item["reasons"], ensure_ascii=False)),
            )


def _write_report(settings: Settings, run_id: int, mode: str, decisions: List[Dict[str, object]]) -> Path:
    directory = settings.output_dir / "product_operations"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    path = directory / ("%s-%s-run%s.json" % (stamp, mode, run_id))
    path.write_text(json.dumps({"run_id": run_id, "mode": mode, "decisions": decisions}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _finish_run(settings: Settings, run_id: int, decisions: List[Dict[str, object]], report_path: Path) -> Dict[str, int]:
    replaced = sum(1 for item in decisions if str(item["decision"]).startswith("replaced"))
    kept = sum(1 for item in decisions if item["decision"] in {"kept", "refreshed"})
    issues = sum(1 for item in decisions if item["decision"] in {"watch", "issue_no_replacement", "api_error"})
    with transaction(settings.database_path) as conn:
        conn.execute(
            """UPDATE product_operation_runs SET status='success', finished_at=CURRENT_TIMESTAMP,
            checked_count=?, kept_count=?, replaced_count=?, issue_count=?, report_path=? WHERE id=?""",
            (len(decisions), kept, replaced, issues, str(report_path), run_id),
        )
    return {"checked": len(decisions), "kept": kept, "replaced": replaced, "issues": issues}


def _age_days(value: str) -> int:
    if not value:
        return 9999
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).days)
    except ValueError:
        try:
            return (date.today() - date.fromisoformat(value[:10])).days
        except ValueError:
            return 9999
