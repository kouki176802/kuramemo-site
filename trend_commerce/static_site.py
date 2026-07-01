from __future__ import annotations

import csv
import html
import json
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List

from .catalog import import_offers, list_offers
from .database import initialize
from .models import Offer
from .settings import ROOT, Settings
from .utils import normalize_text


@dataclass(frozen=True)
class SitePage:
    slug: str
    title: str
    source_path: Path
    markdown: str
    kind: str


ARTICLE_TARGETS = {
    "ai-tool-selection": ("ai-tools-comparison", "AI・ガジェット"),
    "charger-selection": ("charging-power-items-comparison", "AI・ガジェット"),
    "skincare-beginner": ("skincare-basics-comparison", "美容"),
    "home-training-items": ("home-training-items-comparison", "フィットネス"),
    "seasonal-living-heat": ("heat-relief-items-comparison", "季節・暮らし"),
}


def build_static_site(settings: Settings, output_dir: Path | None = None) -> Dict[str, object]:
    """Build a small static comparison site.

    Only active offers with an affiliate_url are rendered as product links.
    Research/pending offers are shown as internal notes so the site can be
    published without pretending that unapproved links are live.
    """

    initialize(settings.database_path)
    import_offers(settings)
    target = output_dir or settings.output_dir / "site"
    if target.exists():
        # Keep the root directory inode stable because Docker bind-mounts it
        # into the WordPress theme. Replacing the directory makes WordPress
        # keep reading the old, now-empty mount until the container restarts.
        for child in target.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        target.mkdir(parents=True, exist_ok=True)

    offers = {offer.offer_id: offer for offer in list_offers(settings)}
    offer_assets = _load_offer_assets(ROOT / "data" / "offer_assets.csv")
    product_map = _load_comparison_product_map(ROOT / "data" / "comparison_product_map.csv")
    trend_rows = _load_trend_opportunities(settings.output_dir / "trends" / "latest_trend_opportunities.csv")
    pages = _load_pages()
    slugs = {page.slug for page in pages}

    css_path = target / "styles.css"
    css_path.write_text(_styles(), encoding="utf-8")
    (target / "click-tracker.js").write_text(_click_tracker_js(), encoding="utf-8")
    _copy_static_assets(target)

    rendered = []
    for page in pages:
        page_markdown = page.markdown
        rows = product_map.get(page.slug, [])
        category_body_prefix = ""
        if page.slug.startswith("category-") and page.slug != "category-services":
            page_markdown = _strip_first_h1(page_markdown)
            category_body_prefix = render_category_intro(page, pages, product_map, offers, offer_assets, trend_rows)
        if page.kind == "comparison":
            page_markdown = _strip_first_h1(page_markdown)
            page_markdown = _prepare_comparison_markdown(page_markdown)
        body = markdown_to_html(page_markdown)
        if page.slug == "index":
            body = _home_landing(offer_assets, trend_rows)
        if category_body_prefix:
            body = category_body_prefix
        if page.kind == "comparison":
            active_rows = [
                row for row in rows
                if (offer := offers.get(row.get("offer_candidate_id", "")))
                and offer.status == "active" and offer.affiliate_url
            ]
            comparison_rows = active_rows or rows
            body = (
                render_comparison_intro(page, comparison_rows, offers, offer_assets)
                + render_offer_section(page.slug, comparison_rows, offers, offer_assets, trend_rows)
                + render_trend_evidence(page.slug, trend_rows)
                + render_comparison_axis(comparison_rows, offer_assets)
                + body
                + render_related_guides(page, pages, product_map)
            )
        if page.kind == "article":
            target_slug, _ = ARTICLE_TARGETS.get(page.slug, ("index", ""))
            body = (
                '<article class="page-card editorial-article">'
                + body
                + '<aside class="article-next"><span>次に見る</span><strong>候補を比べて確認する</strong>'
                + '<a class="button" href="%s.html">比較ガイドを見る</a></aside></article>' % html.escape(target_slug, quote=True)
            )
        html_doc = render_layout(
            page.title, body, page.slug, slugs, settings.site_base_url,
            settings.ga4_measurement_id, settings.gsc_verification,
        )
        out = target / ("%s.html" % page.slug if page.slug != "index" else "index.html")
        out.write_text(html_doc, encoding="utf-8")
        rendered.append(str(out))

    _write_robots(target, settings.site_base_url)
    if settings.site_base_url:
        (target / "CNAME").write_text(settings.site_base_url.split("://", 1)[-1].split("/", 1)[0] + "\n", encoding="utf-8")
        sitemap = _write_sitemap(target, settings.site_base_url, rendered)
        rendered.append(str(sitemap))

    return {
        "output_dir": str(target),
        "pages": len(rendered),
        "files": rendered,
        "active_affiliate_offers": sum(1 for offer in offers.values() if offer.status == "active" and offer.affiliate_url),
    }


def render_related_guides(
    page: SitePage,
    pages: List[SitePage],
    product_map: Dict[str, List[Dict[str, str]]],
) -> str:
    rows = product_map.get(page.slug, [])
    category = rows[0].get("category", "") if rows else ""
    if not category:
        return ""
    page_by_slug = {item.slug: item for item in pages}
    links = []
    for slug, candidate_rows in product_map.items():
        if slug == page.slug or not candidate_rows or candidate_rows[0].get("category") != category:
            continue
        related = page_by_slug.get(slug)
        if not related:
            continue
        links.append(
            '<a href="%s.html"><span>関連ガイド</span><strong>%s</strong><small>%s候補を確認</small></a>' % (
                html.escape(slug, quote=True),
                html.escape(_short_category_card_title(related.title)),
                len(candidate_rows),
            )
        )
    if not links:
        return ""
    return '<section class="related-guides"><div class="section-kicker">関連ガイド</div><h2>同じカテゴリから探す</h2><div>%s</div></section>' % "".join(links[:4])


def _load_pages() -> List[SitePage]:
    pages: List[SitePage] = []
    site_content = ROOT / "site_content"
    for path in sorted(site_content.glob("*.md")):
        slug = _site_content_slug(path)
        text = path.read_text(encoding="utf-8")
        pages.append(SitePage(slug=slug, title=_title_from_markdown(text, slug), source_path=path, markdown=text, kind="page"))

    comparison_dir = ROOT / "samples" / "comparison_pages"
    for path in sorted(comparison_dir.glob("*.md")):
        slug = _comparison_slug(path)
        text = path.read_text(encoding="utf-8")
        pages.append(SitePage(slug=slug, title=_title_from_markdown(text, slug), source_path=path, markdown=text, kind="comparison"))
    article_dir = ROOT / "samples" / "articles"
    for path in sorted(article_dir.glob("*.md")):
        slug = _comparison_slug(path)
        text = path.read_text(encoding="utf-8")
        pages.append(SitePage(slug=slug, title=_title_from_markdown(text, slug), source_path=path, markdown=text, kind="article"))
    return pages


def _site_content_slug(path: Path) -> str:
    if path.stem == "homepage":
        return "index"
    return path.stem.replace("_", "-").replace("-template", "")


def _comparison_slug(path: Path) -> str:
    stem = re.sub(r"^\d+_", "", path.stem)
    if stem == "mens_skincare_beginner":
        stem = "skincare_beginner"
    return stem.replace("_", "-")


def _title_from_markdown(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback.replace("-", " ")


def _strip_first_h1(markdown: str) -> str:
    lines = markdown.splitlines()
    stripped = False
    kept: List[str] = []
    for line in lines:
        if not stripped and line.startswith("# "):
            stripped = True
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _prepare_comparison_markdown(markdown: str) -> str:
    markdown = _remove_markdown_sections(markdown, {"このページの使い方"})
    replacements = {
        "## まず無料でできること": "## 買う前に試せること",
    }
    for before, after in replacements.items():
        markdown = markdown.replace(before, after)
    return markdown


def _remove_markdown_sections(markdown: str, headings: set[str]) -> str:
    lines = markdown.splitlines()
    kept: List[str] = []
    skip_level = 0
    for line in lines:
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            if skip_level and level <= skip_level:
                skip_level = 0
            if title in headings:
                skip_level = level
                continue
        if skip_level:
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _load_comparison_product_map(path: Path) -> Dict[str, List[Dict[str, str]]]:
    result: Dict[str, List[Dict[str, str]]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            result.setdefault(row["page_slug"], []).append(row)
    for rows in result.values():
        rows.sort(key=lambda row: row.get("priority", "Z"))
    return result


def _load_offer_assets(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["offer_id"]: row for row in csv.DictReader(handle)}


def _load_trend_opportunities(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rules_path = ROOT / "data" / "trend_topic_rules.csv"
    with rules_path.open(encoding="utf-8-sig", newline="") as handle:
        rules = {row["rule_id"]: row for row in csv.DictReader(handle)}
    product_map_path = ROOT / "data" / "comparison_product_map.csv"
    with product_map_path.open(encoding="utf-8-sig", newline="") as handle:
        product_groups = {
            row.get("offer_candidate_id", ""): row.get("product_group", "")
            for row in csv.DictReader(handle)
        }
    valid: List[Dict[str, str]] = []
    for row in rows:
        rule = rules.get(row.get("rule_id", ""))
        if not rule:
            continue
        evidence = normalize_text("%s %s" % (row.get("topic", ""), row.get("news_title", "")))
        product = normalize_text(row.get("item_name", ""))
        if row.get("rule_id") == "wellness" and any(term in evidence for term in ["プロテイン", "protein", "クレアチン", "creatine", "eaa", "bcaa"]):
            continue
        terms = [normalize_text(term) for term in rule.get("product_terms", "").split("|") if term]
        focused = [term for term in terms if term in evidence]
        if focused and not any(term in product for term in focused):
            continue
        row["product_group"] = product_groups.get(row.get("item_code", ""), "")
        valid.append(row)
    return valid


def render_trend_evidence(page_slug: str, rows: List[Dict[str, str]]) -> str:
    selected = [row for row in rows if row.get("page_slug") == page_slug][:2]
    if not selected:
        return ""
    cards = []
    for row in selected:
        rank = row.get("rank", "")
        rank_label = "楽天リアルタイム %s位" % rank if rank else "楽天リアルタイム上位"
        checked_label = _checked_date_label(row.get("checked_at", ""))
        news_link = ""
        if row.get("news_url"):
            news_link = '<a class="trend-source-link" href="%s" rel="noopener" target="_blank">報道元を確認</a>' % html.escape(row["news_url"], quote=True)
        image = ""
        if row.get("image_url"):
            image = '<img src="%s" alt="%sの商品画像" loading="lazy">' % (
                html.escape(row["image_url"], quote=True),
                html.escape(_compact_product_name(row.get("item_name", "商品"), 28), quote=True),
            )
        affiliate = row.get("affiliate_url") or row.get("item_url") or ""
        cta = ""
        if affiliate:
            cta = (
                '<a class="button affiliate-link" href="%s" rel="nofollow sponsored noopener" target="_blank" '
                'data-offer-id="trend_%s" data-page-slug="%s" data-network="rakuten" data-product-group="trend-ranking">楽天で詳細を確認</a>'
            ) % (
                html.escape(affiliate, quote=True),
                html.escape(row.get("item_code", ""), quote=True),
                html.escape(page_slug, quote=True),
            )
        review = ""
        if row.get("review_count"):
            review = "レビュー%s件 / ★%s" % (
                html.escape(row["review_count"]), html.escape(row.get("review_average", "")),
            )
        cards.append(
            """
<article class="trend-evidence-card">
  <div class="trend-evidence-copy">
    <div class="trend-badges"><span>%s</span><b>%s</b><small>%s</small></div>
    <h2>%s</h2>
    <p class="trend-why">%s</p>
    <p class="trend-audience"><b>こんな時に</b>%s</p>
    <div class="trend-product-mini">
      <div>%s</div>
      <p><strong>%s</strong><small>%s%s</small></p>
    </div>
    <div class="trend-actions">%s%s</div>
    <small class="trend-disclaimer">%s</small>
  </div>
</article>
""" % (
                html.escape(_trend_market_label(row)),
                html.escape(rank_label),
                html.escape(checked_label),
                html.escape(_shorten_display(row.get("topic", "注目商品"), 54)),
                html.escape(row.get("why_trending", "")),
                html.escape(row.get("context", "用途を確認したい時")),
                image,
                html.escape(_compact_product_name(row.get("item_name", "商品候補"), 48)),
                ("¥%s / " % html.escape(row["price"])) if row.get("price") else "",
                review,
                cta,
                news_link,
                html.escape(row.get("person_note") or "ニュース掲載品と楽天候補は同一商品とは限りません。価格・在庫はリンク先で確認してください。"),
            )
        )
    return (
        '<section class="trend-evidence" id="trend-evidence">'
        '<div class="section-kicker">話題の根拠</div>'
        '<h2>どこで なぜ話題か</h2>'
        '<p class="trend-evidence-lead">日本の現在の注目と、海外の検索急上昇を分けて確認しています。海外の話題は日本で購入できる関連商品がある場合だけ紹介します。</p>'
        + "".join(cards)
        + "</section>"
    )


def _checked_date_label(value: str) -> str:
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value or "")
    if not match:
        return "取得時点を確認"
    return "%s/%s/%s取得" % (match.group(1), match.group(2), match.group(3))


def render_category_intro(
    page: SitePage,
    pages: List[SitePage],
    product_map: Dict[str, List[Dict[str, str]]],
    offers: Dict[str, Offer],
    offer_assets: Dict[str, Dict[str, str]],
    trend_rows: List[Dict[str, str]],
) -> str:
    comparison_pages = {item.slug: item for item in pages if item.kind == "comparison"}
    matches = [
        (slug, rows)
        for slug, rows in product_map.items()
        if rows and rows[0].get("category") == page.title and slug in comparison_pages
    ]
    category_order = {
        "AI・ガジェット": [
            "ai-tools-comparison",
            "charging-power-items-comparison",
            "pc-accessories-comparison",
        ],
    }
    preferred = category_order.get(page.title, [])
    matches.sort(
        key=lambda item: (
            preferred.index(item[0]) if item[0] in preferred else len(preferred),
            comparison_pages[item[0]].title,
        )
    )
    cards = "\n".join(_category_comparison_card(comparison_pages[slug], rows, offers) for slug, rows in matches)
    if page.title == "AI・ガジェット":
        cards += """
<a class="category-comparison-card category-service-card" href="ai-school-services.html">
  <span>Service guide / 4社</span>
  <h2>AIスクール</h2>
  <p>生成AI活用、Python、個別支援、契約条件から学び方を比較します。</p>
  <small>見る軸: 学習内容 / 料金 / 質問対応 / 解約条件</small>
</a>
"""
    product_cards = render_category_product_shelf(page.slug, matches, offers, offer_assets, trend_rows)
    article_cards = render_category_articles(page, pages)
    profile = _category_profile(page.title)
    playbook = "\n".join(
        "<li><b>%s</b><span>%s</span></li>" % (html.escape(title), html.escape(text))
        for title, text in profile["playbook"]
    )
    return """
<section class="category-hero">
  <div>
    <div class="section-kicker">%s</div>
    <h1>%s</h1>
    <p>%s</p>
  </div>
</section>
%s
%s
%s
<section class="category-playbook">
  <div>
    <div class="section-kicker">選ぶ前の確認</div>
    <h2>%s</h2>
    <p>%s</p>
  </div>
  <ul>%s</ul>
</section>
""" % (
        html.escape(profile["kicker"]),
        _inline(page.title),
        html.escape(profile["lead"]).replace("\n", "<br>"),
        '<section class="category-comparison-grid">%s</section>' % cards if cards else "",
        product_cards,
        article_cards,
        html.escape(profile["playbook_title"]),
        html.escape(profile["playbook_lead"]),
        playbook,
    )


def render_category_articles(page: SitePage, pages: List[SitePage]) -> str:
    articles = [
        item for item in pages
        if item.kind == "article" and ARTICLE_TARGETS.get(item.slug, ("", ""))[1] == page.title
    ]
    if not articles:
        return ""
    cards = "".join(
        '<a href="%s.html"><span>読みもの</span><strong>%s</strong><small>選ぶ前の基礎を確認</small></a>' % (
            html.escape(item.slug, quote=True), html.escape(_clean_heading_text(item.title))
        ) for item in articles
    )
    return '<section class="category-articles"><div class="section-kicker">選ぶ前の基礎</div><h2>選ぶ前に読む</h2><div>%s</div></section>' % cards


def _category_comparison_card(page: SitePage, rows: List[Dict[str, str]], offers: Dict[str, Offer]) -> str:
    active_rows = [
        row for row in rows
        if (offer := offers.get(row.get("offer_candidate_id", "")))
        and offer.status == "active" and offer.affiliate_url
    ]
    rows = active_rows or rows
    groups = list(dict.fromkeys(row.get("product_group", "") for row in rows if row.get("product_group")))
    points = _unique_comparison_points(rows)
    return """
<a class="category-comparison-card" href="%s.html">
  <span>Guide / %s候補</span>
  <h2>%s</h2>
  <p>%s</p>
  <small>%s</small>
</a>
""" % (
        html.escape(page.slug, quote=True),
        len(groups),
        _inline(_short_category_card_title(page.title)),
        html.escape(_category_card_summary(groups, points)),
        html.escape("見る軸: " + (" / ".join(points[:4]) if points else "価格 / レビュー / 注意点")),
    )


def render_category_product_shelf(
    category_slug: str,
    matches: List[tuple[str, List[Dict[str, str]]]],
    offers: Dict[str, Offer],
    offer_assets: Dict[str, Dict[str, str]],
    trend_rows: List[Dict[str, str]],
) -> str:
    cards: List[str] = []
    card_limit = 12 if category_slug == "category-housework-timesaving" else 8
    page_slugs = {page_slug for page_slug, _ in matches}
    category_trends = [trend for trend in _ordered_home_trends(trend_rows) if trend.get("page_slug") in page_slugs]
    trend_by_offer = {
        trend.get("item_code", ""): trend
        for trend in category_trends[:2]
        if trend.get("item_code")
    }
    candidates = []
    original_order = 0
    for page_slug, rows in matches:
        for row in rows:
            offer_id = row.get("offer_candidate_id", "")
            offer = offers.get(offer_id)
            if not offer or offer.status != "active" or not offer.affiliate_url:
                continue
            candidates.append((page_slug, row, offer, original_order))
            original_order += 1
    candidates.sort(key=lambda item: (item[2].offer_id not in trend_by_offer, item[3]))
    for page_slug, row, offer, _ in candidates[:card_limit]:
        offer_id = offer.offer_id
        cards.append(_category_product_card(
            category_slug,
            page_slug,
            row,
            offer,
            offer_assets.get(offer_id, {}),
            len(cards) + 1,
            trend_by_offer.get(offer_id),
        ))
    if not cards:
        return ""
    return """
<section class="category-product-shelf" id="category-products">
  <div class="section-kicker">注目商品</div>
  <h2>このカテゴリの注目候補</h2>
  <p>各ページの選定軸から、販売中・レビュー・価格帯・用途一致を確認できた候補を先に並べています。</p>
  <div class="category-product-grid">
    %s
  </div>
</section>
""" % "\n".join(cards)


def _category_product_card(
    category_slug: str,
    page_slug: str,
    row: Dict[str, str],
    offer: Offer,
    asset: Dict[str, str],
    index: int,
    trend: Dict[str, str] | None = None,
) -> str:
    image_html = _offer_image(asset, _category_offer_title(offer, row.get("product_group", "")))
    stats = _compact_asset_stats(asset)
    introduction = _product_introduction(row, asset)
    review_note = _review_reference(asset)
    checks = [point.strip() for point in row.get("comparison_points", "").split("|") if point.strip()]
    check_text = "・".join(checks[:3]) or "価格・仕様・返品条件"
    signal_class, signal_label, signal_detail = _category_product_signal(asset, trend)
    trend_reason = _category_trend_reason(trend) if trend else ""
    return """
<article class="category-product-card">
  <a class="category-product-image" href="%s" rel="nofollow sponsored noopener" target="_blank" data-offer-id="%s" data-page-slug="%s" data-network="%s" data-product-group="%s">%s</a>
  <div>
    <div class="category-product-signal %s"><b>%s</b><small>%s</small></div>
    <span>No.%02d / %s</span>
    <h3>%s</h3>
    <p class="category-product-intro">%s</p>
    %s
    <div class="category-product-reasons">
      <p><b>向いている人</b>%s</p>
      <p><b>レビュー参考</b>%s</p>
      <p><b>購入前の確認</b>%s</p>
    </div>
    <small>%s</small>
    <div class="category-product-actions">
      <a class="button affiliate-link" href="%s" rel="nofollow sponsored noopener" target="_blank" data-offer-id="%s" data-page-slug="%s" data-network="%s" data-product-group="%s">楽天で確認</a>
      <a class="category-guide-link" href="%s.html#affiliate-links">選び方を見る</a>
    </div>
  </div>
</article>
""" % (
        html.escape(offer.affiliate_url, quote=True),
        html.escape(offer.offer_id, quote=True),
        html.escape(category_slug, quote=True),
        html.escape(offer.network, quote=True),
        html.escape(row.get("product_group", ""), quote=True),
        image_html,
        html.escape(signal_class, quote=True),
        html.escape(signal_label),
        html.escape(signal_detail),
        index,
        html.escape(row.get("product_group", "候補")),
        html.escape(_category_offer_title(offer, row.get("product_group", ""))),
        html.escape(introduction),
        trend_reason,
        html.escape(row.get("reader_problem", "").replace("したい", "したい人")),
        html.escape(review_note),
        html.escape(check_text),
        html.escape(stats or row.get("comparison_points", "").replace("|", " / ")),
        html.escape(offer.affiliate_url, quote=True),
        html.escape(offer.offer_id, quote=True),
        html.escape(category_slug, quote=True),
        html.escape(offer.network, quote=True),
        html.escape(row.get("product_group", ""), quote=True),
        html.escape(page_slug, quote=True),
    )


def _category_product_signal(asset: Dict[str, str], trend: Dict[str, str] | None) -> tuple[str, str, str]:
    if trend:
        return "signal-trending", "今話題", _trend_market_label(trend)
    reviews = _safe_int(asset.get("review_count", "0"))
    if reviews >= 500:
        return "signal-reviews", "口コミ多数", "レビュー%s件" % f"{reviews:,}"
    return "signal-purpose", "用途一致", "選定条件を確認"


def _category_trend_reason(trend: Dict[str, str]) -> str:
    source = trend.get("news_source") or "ニュース・検索データ"
    topic = _shorten_display(trend.get("topic", "関連テーマが注目されています"), 64)
    if _is_japan_trend(trend):
        reason = "%sで「%s」が話題。用途が近い販売中候補として紹介しています。" % (source, topic)
    else:
        reason = "%s。%sで「%s」が話題。日本で購入できる関連候補です。" % (
            _trend_market_label(trend), source, topic,
        )
    return (
        '<div class="category-trend-reason"><b>なぜ今？</b><p>%s</p>'
        '<small>ニュース掲載品とは異なる場合があります</small></div>' % html.escape(reason)
    )


def _product_introduction(row: Dict[str, str], asset: Dict[str, str]) -> str:
    """Create an evidence-bound intro without inventing hands-on experience."""
    group = row.get("product_group", "商品")
    problem = row.get("reader_problem", "").strip()
    templates = {
        "ロボット掃除機": "毎日の床掃除を機械に任せたい人向け。水拭き対応の候補なので、吸引力だけでなく段差と手入れの手間まで見て選びます。",
        "布団乾燥機": "天候に左右されず寝具を乾かしたい人向け。布団以外に靴や衣類へ使えるか、ホースの扱いやすさも判断材料です。",
        "衣類スチーマー": "出かける前のしわ取りを短くしたい人向け。アイロン台なしで使いやすい一方、厚手衣類まで整えたい人は出力と重さを要確認です。",
        "電気圧力鍋": "火加減を見る時間を減らしたい人向け。自動調理の便利さだけでなく、実容量・洗う部品・置き場所まで含めて考えます。",
        "除湿機・部屋干し": "雨の日や旅行先で衣類を乾かしやすくしたい人向け。小型タイプは収納しやすい反面、部屋全体の除湿力とは分けて判断します。",
    }
    if group in templates:
        return templates[group]
    points = [point.strip() for point in row.get("comparison_points", "").split("|") if point.strip()]
    axis = "・".join(points[:2]) if points else "価格と使い勝手"
    if problem:
        return "%s人向けの候補です。%sを中心に、買った後の使いやすさまで確認します。" % (
            problem.replace("したい", "したい"), axis
        )
    return "%sは、%sを中心に選ぶと失敗を減らしやすい商品です。" % (group, axis)


def _category_offer_title(offer: Offer, product_group: str) -> str:
    curated = {
        "robot_vacuum_research": "AiMY 水拭き対応ロボット掃除機",
        "futon_dryer_research": "マット不要・靴にも使える布団乾燥機",
        "garment_steamer_research": "2WAY ハンディ衣類スチーマー",
        "electric_pressure_cooker_research": "DELISH KITCHEN 電気圧力鍋 2.0L",
        "dehumidifier_laundry_research": "小型衣類乾燥機 ぽけどらいトラベル",
    }
    return curated.get(offer.offer_id, _compact_product_name(offer.name or product_group, 38))


def _review_reference(asset: Dict[str, str]) -> str:
    reviews = _safe_int(asset.get("review_count", "0"))
    average = asset.get("review_average", "")
    if reviews and average and average != "0.0":
        if reviews >= 500:
            context = "投稿数が多く、評価の母数を取りやすい候補"
        elif reviews >= 50:
            context = "一定数の購入者評価を確認できる候補"
        else:
            context = "件数が少ないため、低評価内容も確認したい候補"
        return "楽天で★%s／%s件。%sです。" % (str(average)[:4], f"{reviews:,}", context)
    return "評価件数が十分でないため、販売ページの新しいレビューと返品条件を要確認です。"


def _short_category_card_title(title: str) -> str:
    title = title.split("｜", 1)[0].strip()
    replacements = {
        "AIツール比較": "AIツール入門",
        "AIツール・周辺ガジェット比較": "AIツール",
        "ai tools comparison": "AIツール入門",
        "充電・モバイル電源比較": "充電・モバイル電源",
        "スキンケア初心者向け比較": "スキンケア",
        "ヘア・身だしなみ用品比較": "ヘア＆セルフケア",
        "ヘア＆セルフケア用品比較": "ヘア＆セルフケア",
        "PC周辺機器比較": "PC周辺機器",
        "家トレ用品比較": "家トレ用品",
        "暑さ対策グッズ比較": "暑さ対策グッズ",
    }
    return replacements.get(title, title.replace("比較", "").strip() or title)


def _category_card_summary(groups: List[str], points: List[str]) -> str:
    group_text = "・".join(groups[:3]) if groups else "候補"
    point_text = "・".join(points[:3]) if points else "価格・レビュー・注意点"
    return "%sを、%sでチェック。" % (group_text, point_text)


def _category_profile(title: str) -> Dict[str, object]:
    profiles: Dict[str, Dict[str, object]] = {
        "AI・ガジェット": {
            "kicker": "AIツールとデジタル用品",
            "lead": "AIツールとPC周辺機器を目的別に整理。\n充電器とモバイルバッテリーは一緒に選べます。",
            "playbook_title": "選ぶ前の3チェック",
            "playbook_lead": "スペック表より先に、失敗しやすい条件だけ見る。",
            "playbook": [
                ("月額か買い切りか", "AI系は無料枠、商用利用、解約条件まで見る。ガジェットは保証と返品条件を先に確認。"),
                ("手持ち機器との相性", "USB-C、PD、容量、対応W数など、スペックが合わないと便利さが出ません。"),
                ("毎日使う理由", "話題性より、通勤・作業・外出で本当に使う場面があるかを優先します。"),
            ],
            "next_items": ["USB-Cケーブル", "AI議事録ツール", "AI画像生成", "PC周辺小物"],
        },
        "美容": {
            "kicker": "美容とセルフケア",
            "lead": "スキンケア、ヘアスタイリング、美容家電。毎日使えるものを手間と使用感で選びます。",
            "playbook_title": "選ぶ前の3チェック",
            "playbook_lead": "見た目の印象より、使い続けられる条件を先に見る。",
            "playbook": [
                ("使う部位と手順", "肌、髪、髭、体毛など、使う場所と順番が明確なものを選ぶ。"),
                ("手入れと消耗品", "替刃、清掃、容量、使用頻度まで含めて負担を見る。"),
                ("合わない時の対応", "肌に触れる商品は注意事項、保証、返品条件を確認する。"),
            ],
            "next_items": ["ヘアワックス", "家庭用脱毛器", "電気シェーバー", "美容家電"],
        },
        "フィットネス": {
            "kicker": "運動用品と栄養補助",
            "lead": "家トレ用品、プロテイン、クレアチン。運動目的と続けやすさで必要なものだけ選びます。",
            "playbook_title": "始める前の3チェック",
            "playbook_lead": "道具や補助食品より、続けられる運動習慣を先に作る。",
            "playbook": [
                ("運動目的", "自重トレ、筋力トレーニング、ストレッチで必要な道具を分ける。"),
                ("置き場所と安全", "音、床、収納、負荷を確認し無理なく使えるものを選ぶ。"),
                ("原材料と継続費", "補助食品は1回量、アレルゲン、1食価格、定期条件を見る。"),
            ],
            "next_items": ["クレアチン", "EAA・BCAA", "トレーニングベンチ", "ストレッチ用品"],
        },
        "健康": {
            "kicker": "毎日の健康補助",
            "lead": "ビタミン、食物繊維、乳酸菌。食生活を補助する商品を成分と1日量で整理します。",
            "playbook_title": "選ぶ前の3チェック",
            "playbook_lead": "何となく増やさず、不足理由と重複摂取を先に確認する。",
            "playbook": [
                ("補いたい理由", "普段の食事を見て、何を補いたいのかを具体的にする。"),
                ("成分と1日量", "栄養成分表示、摂取目安、他商品との重複を確認する。"),
                ("注意事項", "服薬中、妊娠・授乳中、持病がある場合は専門家確認を優先する。"),
            ],
            "next_items": ["マルチビタミン", "食物繊維", "乳酸菌", "ミネラル"],
        },
        "季節・暮らし": {
            "kicker": "季節の暮らし",
            "lead": "暑さ、寒さ、梅雨、新生活。急に欲しくなる季節ものを落ち着いて選びます。",
            "playbook_title": "選ぶ前の3チェック",
            "playbook_lead": "使う場面が決まると、買うべきものも絞れます。",
            "playbook": [
                ("使う場所", "室内、外出、就寝など場面が違うと必要な商品も変わります。"),
                ("置き場所と手入れ", "サイズ、音、掃除、洗濯のしやすさはレビューより先に確認。"),
                ("買わずに済む可能性", "手持ちの家電や環境調整で足りるなら、無理に買わない選択も残します。"),
            ],
            "next_items": ["除湿・部屋干し", "防災用品", "時短家電", "収納用品"],
        },
        "防災・備蓄": {
            "kicker": "防災と備蓄",
            "lead": "停電、断水、避難、在宅備蓄。必要なものを不安ではなく用途で整理します。",
            "playbook_title": "備える前の3チェック",
            "playbook_lead": "家族人数と保管場所から、足りない備えだけを見る。",
            "playbook": [
                ("家用か持ち出しか", "防災リュックと在宅備蓄は役割が違います。まず使う場面を分けます。"),
                ("日数と人数", "水、食料、トイレは人数と日数で必要量が変わります。"),
                ("期限と保管場所", "買って終わりではなく、期限管理できる場所に置けるかを見ます。"),
            ],
            "next_items": ["保存水", "簡易トイレ", "防災ライト", "ポータブル電源"],
        },
        "家事・時短": {
            "kicker": "家事の時短",
            "lead": "掃除、洗濯、料理、衣類ケア。毎日の手間を減らせる候補を整理します。",
            "playbook_title": "時短前の3チェック",
            "playbook_lead": "高機能より、生活動線に合って続くかを見る。",
            "playbook": [
                ("減らしたい家事", "掃除、洗濯、料理のどれを減らすかで候補が変わります。"),
                ("手入れの手間", "便利でも掃除や消耗品が重いと使わなくなります。"),
                ("置き場所と音", "サイズ、収納、運転音は購入前に確認します。"),
            ],
            "next_items": ["ロボット掃除機", "布団乾燥機", "衣類スチーマー", "自動調理鍋"],
        },
        "旅行・外出": {
            "kicker": "旅行と外出",
            "lead": "旅行、出張、帰省、レジャー。荷物を増やしすぎず便利にする候補を見ます。",
            "playbook_title": "出かける前の3チェック",
            "playbook_lead": "便利そうより、持っていく理由があるかを先に見る。",
            "playbook": [
                ("荷物量", "日数と移動手段で必要な容量や収納用品が変わります。"),
                ("移動時間", "長時間移動なら快適グッズ、短時間なら荷物を減らす方を優先します。"),
                ("充電とサイズ制限", "端末数、出力、機内持ち込みサイズを確認します。"),
            ],
            "next_items": ["スーツケース", "圧縮ポーチ", "トラベル充電器", "ネックピロー"],
        },
    }
    return profiles.get(title, {
        "kicker": "買う前の整理",
        "lead": "話題の商品を、使い道と条件から整理するカテゴリです。",
        "playbook_title": "選ぶ前の3チェック",
        "playbook_lead": "迷いやすい条件を先に見る。",
        "playbook": [("用途", "何に使うかを先に決めます。"), ("価格", "継続費用も含めて見ます。"), ("条件", "保証と返品条件を確認します。")],
        "next_items": ["追加テーマ"],
    })


def render_comparison_intro(
    page: SitePage,
    rows: List[Dict[str, str]],
    offers: Dict[str, Offer],
    offer_assets: Dict[str, Dict[str, str]] | None = None,
) -> str:
    groups = [row.get("product_group", "") for row in rows if row.get("product_group")]
    category = rows[0].get("category", "比較") if rows else "比較"
    active_count = sum(
        1
        for row in rows
        if (offer := offers.get(row.get("offer_candidate_id", ""))) and offer.status == "active" and offer.affiliate_url
    )
    points = _unique_comparison_points(rows)
    top_points = "・".join(points[:4]) if points else "価格・レビュー・条件"
    lead_groups = "・".join(groups[:4]) if groups else "候補商品"
    title_main, title_sub = _split_comparison_title(page.title)
    previews = "\n".join(_comparison_hero_preview(row, offer_assets or {}) for row in rows[:3])
    return """
<section class="comparison-hero">
  <div class="comparison-hero-copy">
    <div class="section-kicker">選び方ガイド / %s</div>
    <h1>%s</h1>
    %s
    <p>%sを、%sでチェック。ランキングの勢いより、使う場面と失敗しやすい条件を先に整理します。</p>
    <div class="comparison-hero-actions">
      <a class="button button-primary" href="#affiliate-links">商品候補を見る</a>
      <a class="button button-secondary" href="#comparison-axis">見る軸を確認</a>
    </div>
  </div>
  <aside class="comparison-hero-panel comparison-hero-products" aria-label="すぐ見られる商品候補">
    <p class="comparison-panel-label">商品へ進む</p>
    <strong>すぐ候補を見る</strong>
    <div class="comparison-preview-list">%s</div>
    <a class="button button-secondary" href="#affiliate-links">商品リンクへ</a>
  </aside>
</section>
""" % (
        html.escape(category),
        _inline(title_main),
        '<p class="comparison-title-sub">%s</p>' % _inline(title_sub) if title_sub else "",
        html.escape(lead_groups),
        html.escape(top_points),
        previews,
    )


def render_comparison_axis(
    rows: List[Dict[str, str]],
    offer_assets: Dict[str, Dict[str, str]] | None = None,
) -> str:
    if not rows:
        return ""
    points = _unique_comparison_points(rows)
    point_chips = "\n".join('<span>%s</span>' % html.escape(point) for point in points[:8])
    axis_cards = "\n".join(_comparison_axis_card(index, row, offer_assets or {}) for index, row in enumerate(rows, 1))
    return """
<section class="comparison-axis" id="comparison-axis">
  <div>
    <div class="section-kicker">Decision points</div>
    <h2>先に見るポイント</h2>
    <p class="section-lead">先に「何を見るか」を決めると、商品ページで迷いにくくなります。このページでは次の軸を優先します。</p>
    <div class="comparison-point-chips">%s</div>
  </div>
  <div class="comparison-axis-grid">%s</div>
</section>
""" % (point_chips, axis_cards)


def _split_comparison_title(title: str) -> tuple[str, str]:
    if "｜" in title:
        main, sub = title.split("｜", 1)
    else:
        main, sub = title, ""
    main = main.replace("比較", "").strip() or main
    return main, sub.strip()


def _comparison_hero_preview(row: Dict[str, str], offer_assets: Dict[str, Dict[str, str]]) -> str:
    product_group = html.escape(row.get("product_group", "候補"))
    asset = offer_assets.get(row.get("offer_candidate_id", ""), {})
    offer_id = asset.get("offer_id", "")
    image_html = ""
    local_path = ROOT / "site_content" / "assets" / "products" / ("%s.jpg" % offer_id)
    if offer_id and local_path.exists():
        image_html = '<img src="%s" alt="%sの商品画像">' % (
            html.escape("assets/products/%s.jpg" % offer_id, quote=True),
            product_group,
        )
    return """
<a href="#affiliate-links">
  <span>%s</span>
  %s
</a>
""" % (product_group, image_html)


def _unique_comparison_points(rows: List[Dict[str, str]]) -> List[str]:
    points: List[str] = []
    for row in rows:
        for point in row.get("comparison_points", "").split("|"):
            point = point.strip()
            if point and point not in points:
                points.append(point)
    return points


def _comparison_axis_card(index: int, row: Dict[str, str], offer_assets: Dict[str, Dict[str, str]]) -> str:
    offer_id = row.get("offer_candidate_id", "")
    asset = offer_assets.get(offer_id, {})
    stats = _compact_asset_stats(asset)
    return """
<article class="comparison-axis-card">
  <span>No.%02d</span>
  <h3>%s</h3>
  <p>%s</p>
  <small>%s</small>
</article>
""" % (
        index,
        html.escape(row.get("product_group", "候補")),
        html.escape(row.get("reader_problem", "買う前に条件を確認したい")),
        html.escape(stats or row.get("comparison_points", "").replace("|", " / ")),
    )


def render_offer_section(
    slug: str,
    rows: List[Dict[str, str]],
    offers: Dict[str, Offer],
    offer_assets: Dict[str, Dict[str, str]] | None = None,
    trend_rows: List[Dict[str, str]] | None = None,
) -> str:
    if not rows:
        return ""
    cards = []
    trend_by_offer = {
        trend.get("item_code", ""): trend
        for trend in (trend_rows or [])
        if trend.get("page_slug") == slug and trend.get("item_code")
    }
    for index, row in enumerate(rows, 1):
        offer = offers.get(row["offer_candidate_id"])
        cards.append(_offer_card(
            row,
            offer,
            (offer_assets or {}).get(row["offer_candidate_id"], {}),
            index,
            trend_by_offer.get(row["offer_candidate_id"]),
        ))
    return """
<section class="offer-section" id="affiliate-links">
  <div class="section-kicker">商品候補</div>
  <h2>用途別に確認する商品候補</h2>
  <p class="section-lead">価格・在庫・仕様・保証・申込条件は変わるため、購入前にリンク先で最新情報を確認してください。商品は販売中・レビュー・価格帯・用途一致をもとに自動選定しています。サービス案件は料金、解約条件、対象者、無料枠を確認します。</p>
  <div class="offer-grid">
    %s
  </div>
  <div class="offer-table-wrap">
    <div class="section-kicker">一覧で確認</div>
    %s
  </div>
</section>
""" % ("\n".join(cards), render_offer_comparison_table(rows, offers, offer_assets or {}))


def render_offer_comparison_table(
    rows: List[Dict[str, str]],
    offers: Dict[str, Offer],
    offer_assets: Dict[str, Dict[str, str]],
) -> str:
    table_rows = []
    for index, row in enumerate(rows, 1):
        offer = offers.get(row.get("offer_candidate_id", ""))
        asset = offer_assets.get(row.get("offer_candidate_id", ""), {})
        status = "掲載中" if offer and offer.status == "active" and offer.affiliate_url else "準備中"
        stats = _compact_asset_stats(asset) if status == "掲載中" else "提携条件を確認中"
        table_rows.append(
            "<tr>"
            "<td><b>No.%02d</b><br>%s</td>"
            "<td>%s</td>"
            "<td>%s</td>"
            "<td>%s</td>"
            "<td><span class=\"status-pill status-%s\">%s</span></td>"
            "</tr>"
            % (
                index,
                html.escape(row.get("product_group", "")),
                html.escape(row.get("reader_problem", "")),
                html.escape(row.get("comparison_points", "").replace("|", " / ")),
                html.escape(stats or "リンク先で価格・レビュー確認"),
                "active" if status == "掲載中" else "pending",
                status,
            )
        )
    return """
<div class="table-wrap offer-compare-wrap">
  <table class="offer-compare-table">
    <thead><tr><th>候補</th><th>向いている悩み</th><th>見るポイント</th><th>目安データ</th><th>状態</th></tr></thead>
    <tbody>%s</tbody>
  </table>
</div>
""" % "\n".join(table_rows)


def _offer_card(
    row: Dict[str, str],
    offer: Offer | None,
    asset: Dict[str, str] | None = None,
    rank: int = 1,
    trend: Dict[str, str] | None = None,
) -> str:
    title = html.escape(row.get("product_group") or row.get("offer_candidate_id", "商品候補"))
    problem = html.escape(row.get("reader_problem", ""))
    points = html.escape(row.get("comparison_points", "").replace("|", " / "))
    if offer and offer.status == "active" and offer.affiliate_url:
        name = html.escape(_compact_product_name(offer.name or title, 42))
        url = html.escape(offer.affiliate_url, quote=True)
        network = html.escape(offer.network)
        image = _offer_image(asset or {}, offer.name or title)
        stats = _offer_stats(asset or {})
        evidence = _offer_listing_reason(row, asset or {}, trend)
        return """
<article class="offer-card offer-card-active">
  <p class="offer-rank">No.%02d</p>
  %s
  <p class="offer-label">%s</p>
  <p class="offer-name">%s</p>
  %s
  %s
  <p class="offer-problem">%s</p>
  <p class="offer-points"><span>見るポイント</span>%s</p>
  <a class="button affiliate-link" href="%s" rel="nofollow sponsored noopener" target="_blank" data-offer-id="%s" data-page-slug="%s" data-network="%s" data-product-group="%s">%s</a>
  <p class="offer-meta">広告リンク / 提携: %s / 未使用商品の体験談ではありません</p>
</article>
""" % (
            rank,
            image,
            title,
            name,
            stats,
            evidence,
            problem,
            points,
            url,
            html.escape(row.get("offer_candidate_id", ""), quote=True),
            html.escape(row.get("page_slug", ""), quote=True),
            network,
            html.escape(row.get("product_group", ""), quote=True),
            _cta_label(network),
            network,
        )
    status = html.escape(offer.status if offer else "not_registered")
    return """
<article class="offer-card offer-card-pending">
  <p class="offer-rank">No.%02d</p>
  <h3>%s</h3>
  <p>%s</p>
  <p><span>比較ポイント:</span> %s</p>
  <p class="pending">商品リンク準備中</p>
  <p class="offer-note">提携条件と公式情報を確認中です。確認が終わるまで商品名やリンクは公開しません。</p>
</article>
""" % (rank, title, problem, points)


def _offer_listing_reason(
    row: Dict[str, str],
    asset: Dict[str, str],
    trend: Dict[str, str] | None,
) -> str:
    if trend:
        source = trend.get("news_source") or "ニュース・検索トレンド"
        topic = _shorten_display(trend.get("topic", "関連テーマが注目されています"), 72)
        if _is_japan_trend(trend):
            reason = (
                "%sで「%s」を確認。話題テーマと用途が近く、販売中・レビュー確認済みの候補として選びました。"
                % (source, topic)
            )
        else:
            reason = (
                "%sで「%s」を確認。海外の話題テーマと用途が近く、日本で購入できる販売中・レビュー確認済みの候補として選びました。"
                % (source, topic)
            )
        return (
            '<div class="offer-evidence offer-evidence-trend">'
            '<span>なぜ今 注目？</span><strong>%s</strong><p>%s</p>'
            '<small>ニュース掲載品とこの商品は同一とは限りません</small></div>'
            % (html.escape(_trend_market_label(trend)), html.escape(reason))
        )
    notes = row.get("notes", "")
    if notes and any(term in notes for term in ("@cosme", "LIPS", "SNS", "韓国", "アメリカ", "受賞", "話題")):
        return (
            '<div class="offer-evidence offer-evidence-trend"><span>注目の根拠</span>'
            '<p>%s</p></div>' % html.escape(notes)
        )
    reviews = _safe_int(asset.get("review_count", "0"))
    average = asset.get("review_average", "")
    verified = []
    if reviews:
        verified.append("レビュー%s件" % f"{reviews:,}")
    if average and average != "0.0":
        verified.append("評価★%s" % str(average)[:4])
    proof = "・".join(verified) or "販売状況と商品情報"
    problem = row.get("reader_problem", "用途に合う商品を探している人")
    points = [point for point in row.get("comparison_points", "").split("|") if point][:3]
    point_text = "・".join(points) or "価格と条件"
    return (
        '<div class="offer-evidence"><span>この商品を載せる理由</span>'
        '<strong>%sを確認</strong><p>%s向けの候補として、%sを比べやすいため掲載しています。</p></div>'
        % (html.escape(proof), html.escape(problem), html.escape(point_text))
    )


def _display_offer_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[【\[].*?[】\]]", "", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" *　")
    keep_terms = [
        "アイリスオーヤマ", "WOOZOO", "Lafuture", "ハンディファン", "携帯扇風機",
        "サーキュレーター", "冷感敷きパッド", "敷きパッド", "冷感", "レノ",
    ]
    found = [term for term in keep_terms if term.lower() in cleaned.lower()]
    if found:
        cleaned = " ".join(dict.fromkeys(found))
    if not cleaned:
        cleaned = name or fallback
    return cleaned[:64] + ("…" if len(cleaned) > 64 else "")


def _compact_product_name(name: str, limit: int = 42) -> str:
    cleaned = re.sub(r"[【\[].*?[】\]]", " ", name or "")
    cleaned = re.sub(r"[＼／◆★☆]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" *　-")
    return _shorten_display(cleaned or name or "商品候補", limit)


def _shorten_display(value: str, limit: int) -> str:
    clean = " ".join((value or "").split())
    return clean if len(clean) <= limit else clean[: max(1, limit - 1)].rstrip() + "…"


def _cta_label(network: str) -> str:
    if network == "rakuten":
        return "楽天で詳細を確認する"
    if network in {"a8", "moshimo", "valuecommerce", "impact", "partnerstack"}:
        return "公式ページで条件を確認する"
    return "詳細を確認する"


def _offer_image(asset: Dict[str, str], alt: str = "商品候補") -> str:
    offer_id = asset.get("offer_id", "")
    alt_text = html.escape(_compact_product_name(alt, 42), quote=True)
    local_path = ROOT / "site_content" / "assets" / "products" / ("%s.jpg" % offer_id)
    if offer_id and local_path.exists():
        return '<div class="offer-visual"><img src="%s" alt="%s" loading="eager"></div>' % (html.escape("assets/products/%s.jpg" % offer_id, quote=True), alt_text)
    image_url = asset.get("image_url", "")
    if image_url:
        return '<div class="offer-visual"><img src="%s" alt="%s" loading="eager"></div>' % (html.escape(image_url, quote=True), alt_text)
    return '<div class="offer-visual offer-visual-fallback" aria-hidden="true"><span>比較</span></div>'


def _offer_stats(asset: Dict[str, str]) -> str:
    parts = []
    price = _safe_int(asset.get("min_price", "0"))
    reviews = _safe_int(asset.get("review_count", "0"))
    average = asset.get("review_average", "")
    score = _safe_int(asset.get("score", "0"))
    if price:
        parts.append("<span>¥%s〜</span>" % f"{price:,}")
    if reviews:
        parts.append("<span>レビュー%s件</span>" % f"{reviews:,}")
    if average and average != "0.0":
        parts.append("<span>★%s</span>" % html.escape(str(average)[:4]))
    if score:
        parts.append("<span>選定%s点</span>" % score)
    if not parts:
        return ""
    return '<div class="offer-stats">%s</div>' % "".join(parts)


def _compact_asset_stats(asset: Dict[str, str]) -> str:
    parts = []
    price = _safe_int(asset.get("min_price", "0"))
    reviews = _safe_int(asset.get("review_count", "0"))
    average = asset.get("review_average", "")
    if price:
        parts.append("¥%s〜" % f"{price:,}")
    if reviews:
        parts.append("レビュー%s件" % f"{reviews:,}")
    if average and average != "0.0":
        parts.append("★%s" % str(average)[:4])
    return " / ".join(parts)


def _safe_int(value: str) -> int:
    try:
        return int(float(value or 0))
    except ValueError:
        return 0


def _copy_static_assets(target: Path) -> None:
    source = ROOT / "site_content" / "assets"
    if source.exists():
        shutil.copytree(source, target / "assets", dirs_exist_ok=True)


def markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    out: List[str] = []
    paragraph: List[str] = []
    list_type = ""
    table: List[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            out.append("<p>%s</p>" % _inline(" ".join(paragraph)))
            paragraph = []

    def flush_list() -> None:
        nonlocal list_type
        if list_type:
            out.append("</%s>" % list_type)
            list_type = ""

    def flush_table() -> None:
        nonlocal table
        if table:
            out.append(_table_to_html(table))
            table = []

    for raw in lines:
        line = raw.strip()
        if not line:
            flush_paragraph()
            flush_list()
            flush_table()
            continue
        if line.startswith("|") and line.endswith("|"):
            flush_paragraph()
            flush_list()
            table.append(line)
            continue
        flush_table()
        if line.startswith("#"):
            flush_paragraph()
            flush_list()
            level = min(len(line) - len(line.lstrip("#")), 4)
            text = _clean_heading_text(line[level:].strip())
            if level == 1:
                out.append("<h1>%s</h1>" % _inline(text))
            else:
                heading_id = _heading_id(text)
                out.append('<h%d id="%s">%s</h%d>' % (level, html.escape(heading_id, quote=True), _inline(text), level))
            continue
        match = re.match(r"^[-*]\s+(.+)$", line)
        if match:
            flush_paragraph()
            if list_type != "ul":
                flush_list()
                out.append("<ul>")
                list_type = "ul"
            out.append("<li>%s</li>" % _inline(match.group(1)))
            continue
        match = re.match(r"^\d+\.\s+(.+)$", line)
        if match:
            flush_paragraph()
            if list_type != "ol":
                flush_list()
                out.append("<ol>")
                list_type = "ol"
            out.append("<li>%s</li>" % _inline(match.group(1)))
            continue
        paragraph.append(line)
    flush_paragraph()
    flush_list()
    flush_table()
    return "\n".join(out)


def _table_to_html(rows: List[str]) -> str:
    parsed = [[cell.strip() for cell in row.strip("|").split("|")] for row in rows]
    if len(parsed) > 1 and all(set(cell) <= {"-", ":", " "} and "-" in cell for cell in parsed[1]):
        header = parsed[0]
        body_rows = parsed[2:]
    else:
        header = []
        body_rows = parsed
    parts = ["<div class=\"table-wrap\"><table>"]
    if header:
        parts.append("<thead><tr>%s</tr></thead>" % "".join("<th>%s</th>" % _inline(cell) for cell in header))
    parts.append("<tbody>")
    for row in body_rows:
        parts.append("<tr>%s</tr>" % "".join("<td>%s</td>" % _inline(cell) for cell in row))
    parts.append("</tbody></table></div>")
    return "\n".join(parts)


def _inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda match: '<a href="%s">%s</a>' % (html.escape(match.group(2), quote=True), match.group(1)),
        escaped,
    )
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def _heading_id(text: str) -> str:
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    cleaned = re.sub(r"[*_`#]", "", cleaned).strip().lower()
    cleaned = re.sub(r"\s+", "-", cleaned)
    cleaned = re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff-]+", "", cleaned)
    return cleaned or "section"


def _clean_heading_text(text: str) -> str:
    return re.sub(r"[、。]+", "", text).strip()


def render_layout(
    title: str,
    body: str,
    slug: str,
    slugs: Iterable[str],
    site_base_url: str = "",
    ga4_measurement_id: str = "",
    gsc_verification: str = "",
) -> str:
    nav_items = [
        ("index", "トップ"),
        ("category-ai-gadgets", "AI・ガジェット"),
        ("category-beauty", "美容"),
        ("category-fitness", "フィットネス"),
        ("category-health", "健康"),
        ("category-lifestyle-seasonal", "季節・暮らし"),
        ("category-disaster-preparedness", "防災・備蓄"),
        ("category-housework-timesaving", "家事・時短"),
        ("category-travel-outdoor", "旅行・外出"),
        ("category-services", "サービス"),
        ("advertising-policy", "広告方針"),
    ]
    slugs_set = set(slugs)
    active_nav_slug = _active_nav_slug(slug)
    nav = "\n".join(
        '<a href="%s.html"%s><span>%s</span></a>' % (
            "index" if item_slug == "index" else item_slug,
            ' aria-current="page"' if item_slug == active_nav_slug else "",
            label,
        )
        for item_slug, label in nav_items
        if item_slug in slugs_set
    )
    main_body = body if slug == "index" else '<section class="page-card">%s</section>' % body
    body_class = "home" if slug == "index" else "subpage"
    document_title = "くらメモ" if slug == "index" else "%s | くらメモ" % title
    description = _meta_description(title, slug)
    page_name = "index.html" if slug == "index" else "%s.html" % slug
    canonical_url = "%s/%s" % (site_base_url.rstrip("/"), page_name) if site_base_url else ""
    canonical = '<link rel="canonical" href="%s">' % html.escape(canonical_url, quote=True) if canonical_url else ""
    robots_meta = '<meta name="robots" content="index,follow,max-image-preview:large">' if site_base_url else '<meta name="robots" content="noindex,nofollow">'
    og_url = '<meta property="og:url" content="%s">' % html.escape(canonical_url, quote=True) if canonical_url else ""
    schema = _schema_json(document_title, description, canonical_url, slug)
    ga4 = _ga4_script(ga4_measurement_id)
    gsc = '<meta name="google-site-verification" content="%s">' % html.escape(gsc_verification, quote=True) if gsc_verification else ""
    return """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>%s</title>
  <meta name="description" content="%s">
  %s
  %s
  <meta property="og:site_name" content="くらメモ">
  <meta property="og:type" content="%s">
  <meta property="og:title" content="%s">
  <meta property="og:description" content="%s">
  %s
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="%s">
  <meta name="twitter:description" content="%s">
  <script type="application/ld+json">%s</script>
  %s
  %s
  <link rel="stylesheet" href="styles.css?v=20260627b">
  <script src="click-tracker.js" defer></script>
</head>
<body class="%s">
  <header class="site-header">
    <a class="brand" href="index.html"><span>くらメモ</span><small>注目商品チェック</small></a>
    <nav aria-label="主要カテゴリ">%s</nav>
  </header>
  <main>
    %s
  </main>
  <footer>
    <p>© くらメモ / 注目商品チェック</p>
    <p><a href="privacy-policy.html">プライバシーポリシー</a>・<a href="disclaimer.html">免責事項</a>・<a href="editorial-policy.html">編集方針</a></p>
  </footer>
</body>
</html>
""" % (
        html.escape(document_title), html.escape(description, quote=True), robots_meta, canonical,
        "article" if slug.endswith("comparison") else "website", html.escape(document_title, quote=True),
        html.escape(description, quote=True), og_url, html.escape(document_title, quote=True),
        html.escape(description, quote=True), schema, gsc, ga4, body_class, nav, main_body,
    )


def _meta_description(title: str, slug: str) -> str:
    if slug == "index":
        return "SNSやニュースで注目される商品を用途・条件・価格で整理する注目商品チェックメディア"
    if slug.startswith("category-"):
        return "%sの商品と選び方を用途・価格・レビュー・注意点から整理します" % title
    if slug.endswith("comparison"):
        return "%sを用途・価格・レビュー・注意点から比較し自分に合う候補を選べます" % title.split("｜", 1)[0]
    return "%sについて、くらメモの運営方針と確認事項を案内します" % title


def _schema_json(title: str, description: str, canonical_url: str, slug: str) -> str:
    page_type = "Article" if slug.endswith("comparison") else ("CollectionPage" if slug.startswith("category-") else "WebPage")
    page: Dict[str, object] = {
        "@type": page_type,
        "name": title,
        "headline": title,
        "description": description,
        "inLanguage": "ja-JP",
        "dateModified": date.today().isoformat(),
        "author": {"@type": "Organization", "name": "くらメモ"},
        "publisher": {"@type": "Organization", "name": "くらメモ"},
    }
    if canonical_url:
        page["url"] = canonical_url
        page["mainEntityOfPage"] = canonical_url
    graph: List[Dict[str, object]] = [page]
    if canonical_url and slug != "index":
        base = canonical_url.rsplit("/", 1)[0]
        category_slug = _active_nav_slug(slug)
        labels = {
            "category-ai-gadgets": "AI・ガジェット", "category-beauty": "美容",
            "category-fitness": "フィットネス", "category-health": "健康",
            "category-lifestyle-seasonal": "季節・暮らし", "category-disaster-preparedness": "防災・備蓄",
            "category-housework-timesaving": "家事・時短", "category-travel-outdoor": "旅行・外出",
            "category-services": "サービス",
        }
        items: List[Dict[str, object]] = [
            {"@type": "ListItem", "position": 1, "name": "トップ", "item": "%s/index.html" % base},
        ]
        if category_slug in labels and category_slug != slug:
            items.append({
                "@type": "ListItem", "position": 2, "name": labels[category_slug],
                "item": "%s/%s.html" % (base, category_slug),
            })
        items.append({"@type": "ListItem", "position": len(items) + 1, "name": title, "item": canonical_url})
        graph.append({"@type": "BreadcrumbList", "itemListElement": items})
    payload: Dict[str, object] = {"@context": "https://schema.org", "@graph": graph}
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def _ga4_script(measurement_id: str) -> str:
    if not measurement_id or not re.fullmatch(r"G-[A-Z0-9]+", measurement_id):
        return ""
    safe_id = html.escape(measurement_id, quote=True)
    return """<script async src="https://www.googletagmanager.com/gtag/js?id=%s"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}gtag('js',new Date());gtag('config','%s');</script>""" % (safe_id, safe_id)


def _write_robots(target: Path, site_base_url: str) -> Path:
    lines = ["User-agent: *", "Allow: /"]
    if site_base_url:
        lines.extend(["", "Sitemap: %s/sitemap.xml" % site_base_url.rstrip("/")])
    else:
        lines = ["User-agent: *", "Disallow: /", "", "# SITE_BASE_URLを設定すると公開用robots.txtへ切り替わります"]
    path = target / "robots.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_sitemap(target: Path, site_base_url: str, rendered: List[str]) -> Path:
    base = site_base_url.rstrip("/")
    today = date.today().isoformat()
    urls = []
    for raw in rendered:
        path = Path(raw)
        if path.suffix != ".html":
            continue
        urls.append("<url><loc>%s/%s</loc><lastmod>%s</lastmod></url>" % (html.escape(base), html.escape(path.name), today))
    content = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>\n' % "".join(urls)
    path = target / "sitemap.xml"
    path.write_text(content, encoding="utf-8")
    return path


def _active_nav_slug(slug: str) -> str:
    category_by_page = {
        "ai-tools-comparison": "category-ai-gadgets",
        "charging-power-items-comparison": "category-ai-gadgets",
        "pc-accessories-comparison": "category-ai-gadgets",
        "skincare-basics-comparison": "category-beauty",
        "hair-grooming-items-comparison": "category-beauty",
        "home-training-items-comparison": "category-fitness",
        "fitness-supplements-comparison": "category-fitness",
        "health-support-supplements-comparison": "category-health",
        "heat-relief-items-comparison": "category-lifestyle-seasonal",
        "disaster-preparedness-items-comparison": "category-disaster-preparedness",
        "housework-timesaving-items-comparison": "category-housework-timesaving",
        "kitchen-appliances-comparison": "category-housework-timesaving",
        "living-appliances-comparison": "category-housework-timesaving",
        "travel-outdoor-items-comparison": "category-travel-outdoor",
        "ai-school-services": "category-services",
        "mobile-carrier-services": "category-services",
        "investment-account-services": "category-services",
    }
    if slug in ARTICLE_TARGETS:
        category = ARTICLE_TARGETS[slug][1]
        article_categories = {
            "AI・ガジェット": "category-ai-gadgets",
            "美容": "category-beauty",
            "フィットネス": "category-fitness",
            "健康": "category-health",
            "季節・暮らし": "category-lifestyle-seasonal",
        }
        return article_categories.get(category, slug)
    return category_by_page.get(slug, slug)


def _click_report_html(slugs: Iterable[str]) -> str:
    body = """
<section class="page-card click-report">
  <h1>クリック分析</h1>
  <p>このページは、同じブラウザ内で保存された商品リンククリックを確認するための簡易レポートです。外部送信はしません。GA4導入前の無料テスト用です。</p>
  <div class="click-report-actions">
    <button class="button" type="button" id="download-click-log">CSVをダウンロード</button>
    <button class="button button-secondary" type="button" id="clear-click-log">ログを削除</button>
  </div>
  <div class="table-wrap">
    <table id="click-summary-table">
      <thead><tr><th>商品ID</th><th>ページ</th><th>商品グループ</th><th>クリック数</th><th>最終クリック</th></tr></thead>
      <tbody><tr><td colspan="5">まだクリックログがありません。</td></tr></tbody>
    </table>
  </div>
  <h2>見るポイント</h2>
  <ul>
    <li>クリックが多い商品は、SNS投稿やランキング記事で横展開します。</li>
    <li>PVがあるのにクリックされないページは、商品カード位置・CTA文言・比較表を見直します。</li>
    <li>クリックはあるのに売れない商品は、価格・レビュー・商品ズレ・販売ページ条件を確認します。</li>
  </ul>
</section>
"""
    return render_layout("クリック分析", body, "click-report", slugs)


def _click_tracker_js() -> str:
    return r"""
(function () {
  const KEY = "erabikata_click_log_v1";

  function readLog() {
    try {
      return JSON.parse(localStorage.getItem(KEY) || "[]");
    } catch (error) {
      return [];
    }
  }

  function writeLog(rows) {
    localStorage.setItem(KEY, JSON.stringify(rows.slice(-1000)));
  }

  function pageSlug() {
    const file = location.pathname.split("/").pop() || "index.html";
    return file.replace(/\.html$/, "") || "index";
  }

  function recordClick(link) {
    const rows = readLog();
    rows.push({
      clicked_at: new Date().toISOString(),
      page_slug: link.dataset.pageSlug || pageSlug(),
      offer_id: link.dataset.offerId || "",
      network: link.dataset.network || "",
      product_group: link.dataset.productGroup || "",
      link_text: (link.textContent || "").trim(),
      href: link.href
    });
    writeLog(rows);
    if (typeof window.gtag === "function") {
      window.gtag("event", "affiliate_click", {
        offer_id: link.dataset.offerId || "",
        product_group: link.dataset.productGroup || "",
        network: link.dataset.network || "",
        page_slug: link.dataset.pageSlug || pageSlug(),
        link_url: link.href
      });
    }
  }

  function csvEscape(value) {
    const text = String(value ?? "");
    return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
  }

  function downloadCsv() {
    const rows = readLog();
    const headers = ["clicked_at", "page_slug", "offer_id", "network", "product_group", "link_text", "href"];
    const csv = [headers.join(",")].concat(rows.map(row => headers.map(key => csvEscape(row[key])).join(","))).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "affiliate_click_log.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function renderReport() {
    const table = document.querySelector("#click-summary-table tbody");
    if (!table) return;
    const rows = readLog();
    const summary = new Map();
    for (const row of rows) {
      const key = [row.offer_id, row.page_slug, row.product_group].join("|");
      const current = summary.get(key) || {
        offer_id: row.offer_id,
        page_slug: row.page_slug,
        product_group: row.product_group,
        clicks: 0,
        last_click: ""
      };
      current.clicks += 1;
      current.last_click = row.clicked_at;
      summary.set(key, current);
    }
    const items = Array.from(summary.values()).sort((a, b) => b.clicks - a.clicks || b.last_click.localeCompare(a.last_click));
    if (!items.length) {
      table.innerHTML = '<tr><td colspan="5">まだクリックログがありません。</td></tr>';
      return;
    }
    table.innerHTML = items.map(item => (
      "<tr>" +
      "<td>" + csvEscape(item.offer_id).replace(/^\"|\"$/g, "") + "</td>" +
      "<td>" + csvEscape(item.page_slug).replace(/^\"|\"$/g, "") + "</td>" +
      "<td>" + csvEscape(item.product_group).replace(/^\"|\"$/g, "") + "</td>" +
      "<td>" + item.clicks + "</td>" +
      "<td>" + item.last_click + "</td>" +
      "</tr>"
    )).join("");
  }

  document.addEventListener("click", function (event) {
    const link = event.target.closest && event.target.closest("a.affiliate-link");
    if (link) recordClick(link);
  });

  document.addEventListener("DOMContentLoaded", function () {
    renderReport();
    const download = document.getElementById("download-click-log");
    const clear = document.getElementById("clear-click-log");
    if (download) download.addEventListener("click", downloadCsv);
    if (clear) clear.addEventListener("click", function () {
      if (confirm("このブラウザに保存されたクリックログを削除しますか？")) {
        localStorage.removeItem(KEY);
        renderReport();
      }
    });
  });
})();
"""


def _home_figure(offer_assets: Dict[str, Dict[str, str]], offer_id: str, alt: str) -> str:
    image_url = offer_assets.get(offer_id, {}).get("image_url", "")
    if not image_url:
        return '<figure class="figure-mark">%s</figure>' % html.escape(alt[:8])
    return '<figure><img src="%s" alt="%s" loading="lazy"></figure>' % (
        html.escape(image_url, quote=True), html.escape(alt, quote=True)
    )


def _home_trend_cards(rows: List[Dict[str, str]]) -> str:
    cards: List[str] = []
    ordered = _ordered_home_trends(rows)
    for row in ordered[:3]:
        image = ""
        if row.get("image_url"):
            image = '<img src="%s" alt="%s" loading="eager">' % (
                html.escape(row["image_url"], quote=True),
                html.escape(_compact_product_name(row.get("item_name", "注目商品"), 30), quote=True),
            )
        cards.append(
            '<a class="home-trend-card" href="%s.html#trend-evidence">%s<div>'
            '<span>%s・%s</span><strong>%s</strong>'
            '<p class="home-trend-trigger"><b>話題のきっかけ</b>%s</p>'
            '<p class="home-trend-reason"><b>なぜ掲載？</b>%s</p>'
            '</div></a>' % (
                html.escape(row.get("page_slug", "index"), quote=True),
                image,
                html.escape(_trend_market_label(row)),
                html.escape(row.get("news_source", "ニュース・検索")),
                html.escape(_trend_display_product(row)),
                html.escape(_shorten_display(row.get("topic", "関連テーマが注目されています"), 48)),
                html.escape(_home_trend_reason(row, 76)),
            )
        )
    if not cards:
        return ""
    return '<section class="home-trend-pulse" id="trend-now"><div><span>ニュース・SNSと海外トレンド</span><h2>どこで なぜ注目されているか</h2></div><div class="home-trend-grid">%s</div></section>' % "".join(cards)


def _ordered_home_trends(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (
            -int(float(row.get("score") or 0)),
            row.get("country_name", "日本") == "日本",
        ),
    )


def _home_trend_reason(row: Dict[str, str], limit: int = 120) -> str:
    source = row.get("news_source") or "ニュース・検索データ"
    market = _trend_market_label(row)
    if _is_japan_trend(row):
        reason = "%sで話題のテーマと用途が近く、販売中・レビュー確認済みの候補です。" % source
    else:
        reason = (
            "%s。%sで話題のテーマと用途が近く、日本で購入できる販売中・レビュー確認済みの候補です。"
            % (market, source)
        )
    return _shorten_display(
        reason,
        limit,
    )


def _trend_display_product(row: Dict[str, str]) -> str:
    group = row.get("product_group", "").strip()
    raw_name = re.sub(r"[【\[].*?[】\]]", " ", row.get("item_name", ""))
    raw_name = re.sub(r"[（(][0-9,\-〜～.\s]+[）)]", " ", raw_name)
    raw_name = re.sub(r"\s+", " ", raw_name).strip()
    brand_match = re.match(r"([A-Za-z][A-Za-z0-9&+.'-]*(?:\s+[A-Za-z0-9&+.'-]+){0,2})", raw_name)
    brand = brand_match.group(1).strip() if brand_match else ""
    if group:
        return _shorten_display((brand + " " + group).strip(), 30)
    return _compact_product_name(raw_name or "注目商品", 30)


def _home_featured_trend(rows: List[Dict[str, str]]) -> tuple[str, str]:
    ordered = _ordered_home_trends(rows)
    if not ordered:
        feature = """
    <a class="hero-feature-card" href="heat-relief-items-comparison.html">
      <span>SNS・ニュース注目</span>
      <strong>暑さ対策グッズ</strong>
      <p>夏の買い物は外出・室内・就寝で候補を分ける</p>
      <div class="hero-product-stack">
        <img src="assets/products/portable_fan_research.jpg" alt="携帯扇風機の商品画像">
        <img src="assets/products/cooling_bedding_research.jpg" alt="冷感寝具の商品画像">
        <img src="assets/products/air_circulator_research.jpg" alt="サーキュレーターの商品画像">
      </div>
    </a>"""
        notes = """
    <div class="hero-notes">
      <a href="heat-relief-items-comparison.html#trend-evidence"><b>01</b><span>なぜ注目か</span></a>
      <a href="heat-relief-items-comparison.html#affiliate-links"><b>02</b><span>商品候補</span></a>
      <a href="heat-relief-items-comparison.html#comparison-axis"><b>03</b><span>向く人を見る</span></a>
    </div>"""
        return feature, notes
    row = ordered[0]
    page_slug = html.escape(row.get("page_slug", "index"), quote=True)
    product_name = html.escape(_trend_display_product(row))
    topic = html.escape(_shorten_display(row.get("topic", "関連テーマが注目されています"), 72))
    market = html.escape(_trend_market_label(row))
    source = html.escape(row.get("news_source") or "ニュース・検索データ")
    reason = html.escape(_home_trend_reason(row, 108))
    image = ""
    if row.get("image_url"):
        image = '<img src="%s" alt="%sの商品画像" loading="eager">' % (
            html.escape(row["image_url"], quote=True), product_name,
        )
    stats = []
    if row.get("price"):
        stats.append("¥%s" % html.escape(row["price"]))
    if row.get("review_count"):
        stats.append("レビュー%s件" % html.escape(row["review_count"]))
    if row.get("review_average"):
        stats.append("★%s" % html.escape(row["review_average"]))
    stats_html = " / ".join(stats)
    feature = """
    <a class="hero-feature-card hero-feature-trend" href="%s.html#trend-evidence">
      <div class="hero-feature-heading"><span>%s・%s</span><strong>%s</strong></div>
      <div class="hero-trend-hook"><b>話題のきっかけ</b><p>%s</p></div>
      <div class="hero-why-highlight"><b>なぜこの商品？</b><p>%s</p></div>
      <div class="hero-product-focus">%s<small>%s</small></div>
      <small class="hero-related-note">ニュース掲載品とは異なる場合があります</small>
    </a>""" % (page_slug, market, source, product_name, topic, reason, image, stats_html)
    notes = """
    <div class="hero-notes">
      <a href="%s.html#trend-evidence"><b>01</b><span>注目の根拠</span></a>
      <a href="%s.html#affiliate-links"><b>02</b><span>商品候補</span></a>
      <a href="%s.html#comparison-axis"><b>03</b><span>向く人を見る</span></a>
    </div>""" % (page_slug, page_slug, page_slug)
    return feature, notes


def _trend_market_label(row: Dict[str, str]) -> str:
    label = row.get("market_label", "")
    country = row.get("country_name", "日本")
    if country == "日本":
        if "ニュース" in label:
            return "ニュースで注目"
        if "検索" in label:
            return "検索で注目"
        return "注目テーマ"
    if label:
        return label.replace("米国", "アメリカ").replace("英国", "イギリス")
    if country == "米国":
        country = "アメリカ"
    elif country == "英国":
        country = "イギリス"
    evidence = row.get("evidence_label", "")
    if "Google Trends" in evidence:
        return "%sで検索急上昇" % country
    if "Googleニュース" in evidence:
        return "%sのニュースで注目" % country
    return "%sで注目" % country


def _is_japan_trend(row: Dict[str, str]) -> bool:
    return row.get("country_name", "日本") == "日本"


def _home_landing(offer_assets: Dict[str, Dict[str, str]], trend_rows: List[Dict[str, str]]) -> str:
    trend_cards = _home_trend_cards(trend_rows)
    featured_trend, featured_notes = _home_featured_trend(trend_rows)
    ordered_trends = _ordered_home_trends(trend_rows)
    featured_slug = html.escape(
        ordered_trends[0].get("page_slug", "heat-relief-items-comparison") if ordered_trends
        else "heat-relief-items-comparison",
        quote=True,
    )
    topic_labels = []
    for trend in ordered_trends:
        label = trend.get("product_group", "")
        if label and label not in topic_labels:
            topic_labels.append(label)
        if len(topic_labels) == 3:
            break
    topic_summary = html.escape(" / ".join(topic_labels) or "暑さ対策 / 防災備蓄 / 旅行外出")
    return """
<section class="hero">
  <div class="hero-copy">
    <div class="eyebrow">SNS・ニュースの注目商品</div>
    <h1><span>SNSとニュースの</span><span>話題を先取り</span></h1>
    <p class="hero-lead">いま注目されている商品やサービスを見つけて<br>用途・条件・価格から選びやすく整理します<br><strong>話題だけで決めず 納得できる一品へ</strong></p>
    <div class="hero-meta">
      <span>Seasonal goods</span>
      <span>Gadgets</span>
      <span>Beauty & fitness</span>
      <span>Preparedness</span>
      <span>Travel</span>
    </div>
    <div class="hero-topic-row">
      <span>いまの注目</span>
      <b>%s</b>
    </div>
    <div class="hero-actions">
      <a class="button button-primary" href="#trend-now">注目の理由をまとめて見る</a>
      <a class="button button-secondary" href="%s.html#affiliate-links">この商品を比較する</a>
    </div>
  </div>
  <div class="hero-showcase" aria-label="注目の選び方">
    %s
    %s
  </div>
</section>
%s
<section class="comparison-index" id="comparison-index">
  <div class="section-kicker">商品ガイド</div>
  <h2>気になるものから開く</h2>
  <div class="article-grid">
    <a class="article-card" href="heat-relief-items-comparison.html">
      <figure><img src="assets/products/portable_fan_research.jpg" alt="携帯扇風機の商品画像"></figure>
      <span>Seasonal</span>
      <h3>暑さ対策グッズ</h3>
      <p>携帯扇風機・冷感寝具・サーキュレーターを夏前に確認</p>
    </a>
    <a class="article-card" href="charging-power-items-comparison.html">%s<span>Gadget</span><h3>充電・モバイル電源</h3><p>充電器・バッテリー・ケーブルをまとめて確認</p></a>
    <a class="article-card" href="category-beauty.html">%s<span>Beauty</span><h3>美容・身だしなみ</h3><p>スキンケア・ヘア用品・美容家電を確認</p></a>
    <a class="article-card" href="category-fitness.html">%s<span>Fitness</span><h3>家トレ・運動補助</h3><p>トレーニング用品・プロテイン・クレアチンを確認</p></a>
    <a class="article-card" href="category-health.html">%s<span>Health</span><h3>健康補助</h3><p>ビタミン・食物繊維・乳酸菌を成分で確認</p></a>
    <a class="article-card" href="ai-tools-comparison.html">%s<span>Tools</span><h3>AIツール</h3><p>無料枠・月額・商用利用の条件を確認</p></a>
    <a class="article-card" href="disaster-preparedness-items-comparison.html">%s<span>Preparedness</span><h3>防災・備蓄グッズ</h3><p>電源・水・トイレ・食料・持ち出しで確認</p></a>
    <a class="article-card" href="category-housework-timesaving.html">%s<span>Daily</span><h3>家事・暮らし家電</h3><p>掃除・洗濯・料理を助ける家電をまとめて確認</p></a>
    <a class="article-card" href="travel-outdoor-items-comparison.html">%s<span>Travel</span><h3>旅行・外出グッズ</h3><p>荷造り・移動・充電・貴重品管理を整理</p></a>
  </div>
</section>
""" % (
        topic_summary,
        featured_slug,
        featured_trend,
        featured_notes,
        trend_cards,
        _home_figure(offer_assets, "usb_c_charger_small_research", "USB-C充電器"),
        _home_figure(offer_assets, "home_hair_removal_research", "美容・身だしなみ用品"),
        _home_figure(offer_assets, "creatine_research", "フィットネス補助食品"),
        _home_figure(offer_assets, "multivitamin_research", "健康補助サプリメント"),
        _home_figure(offer_assets, "ai_voice_recorder_research", "AI・デジタル用品"),
        _home_figure(offer_assets, "portable_power_station_research", "防災・備蓄用品"),
        _home_figure(offer_assets, "robot_vacuum_research", "家事・時短家電"),
        _home_figure(offer_assets, "suitcase_research", "旅行・外出用品"),
    )


def _styles() -> str:
    return """
:root { color-scheme: light; --ink:#111111; --muted:#66615a; --line:#ded8cc; --bg:#f5f1e8; --card:#fffdf7; --accent:#111111; --accent2:#9b6a2f; --soft:#f1f1f1; --paper:#fffaf0; --shadow:0 18px 52px rgba(17, 17, 17, .09); --display:"Gelasio", Georgia, "Hiragino Mincho ProN", "Yu Mincho", serif; --body:-apple-system, BlinkMacSystemFont, "Hiragino Sans", "Noto Sans JP", sans-serif; --mono:"Ubuntu Mono", "SFMono-Regular", ui-monospace, monospace; }
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; font-family: var(--body); color: var(--ink); background:
  linear-gradient(90deg, rgba(17,17,17,.025) 1px, transparent 1px) 0 0 / 64px 64px,
  linear-gradient(180deg, #fbf8f0 0%, var(--bg) 52%, #eee6d9 100%); line-height: 1.85; }
h1, h2, h3, strong, .offer-name { line-break:strict; word-break:auto-phrase; }
body.home { background:
  radial-gradient(circle at 18% 12%, rgba(59,130,246,.12), transparent 28%),
  radial-gradient(circle at 82% 10%, rgba(139,92,246,.12), transparent 30%),
  linear-gradient(180deg, #fbfcff 0%, #f7f3ea 62%, #eee6d9 100%); }
a { color: var(--accent); }
.site-header { position: sticky; top:0; z-index:5; display:flex; gap:24px; justify-content:space-between; align-items:center; padding:14px clamp(18px, 4vw, 42px); border-bottom:1px solid rgba(17,17,17,.12); background:rgba(255,250,240,.86); backdrop-filter: blur(18px); }
.brand { display:flex; flex-direction:column; line-height:1.05; font-family:var(--display); font-weight:900; text-decoration:none; color:var(--ink); letter-spacing:-.04em; font-size:20px; }
.brand small { font-family:var(--mono); color:var(--accent2); font-size:10px; letter-spacing:.12em; text-transform:uppercase; margin-top:5px; }
nav { display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; font-size:13px; }
nav a { position:relative; display:inline-flex; align-items:center; min-height:34px; padding:6px 10px; border:1px solid transparent; border-radius:999px; text-decoration:none; color:var(--muted); font-weight:900; white-space:nowrap; transition:background .2s ease, border-color .2s ease, color .2s ease, transform .2s ease; }
nav a:hover { background:rgba(59,130,246,.08); border-color:rgba(59,130,246,.16); color:#111827; transform:translateY(-1px); }
nav a[aria-current="page"] { color:#111827; background:#fff; border-color:rgba(59,130,246,.24); box-shadow:0 10px 28px rgba(59,130,246,.1); }
nav a[aria-current="page"] span { background:linear-gradient(100deg, #111827, #2563eb); -webkit-background-clip:text; background-clip:text; color:transparent; }
main { width:min(1120px, calc(100% - 24px)); margin:0 auto 44px; }
.hero { display:grid; grid-template-columns: minmax(0, 1.08fr) minmax(320px, .92fr); gap:30px; align-items:center; min-height:550px; padding:56px 0 28px; border-bottom:2px solid var(--ink); }
.home .hero { min-height:590px; padding:62px 0 34px; border-bottom:0; }
.hero-copy { animation:none; }
.eyebrow, .section-kicker { font-family:var(--mono); color:var(--accent2); font-size:13px; font-weight:900; letter-spacing:.16em; text-transform:uppercase; }
.home .eyebrow, .home .section-kicker { color:#3B82F6; }
.hero h1 { max-width:650px; font-family:var(--display); font-size: clamp(46px, 5.25vw, 72px); line-height:.98; letter-spacing:-.065em; margin:18px 0 18px; color:var(--ink); font-weight:900; text-shadow:0 0 0 #111; }
.home .hero h1 { max-width:670px; font-size:clamp(50px, 6vw, 82px); letter-spacing:-.075em; }
.hero h1 span { display:block; }
.hero h1 span:last-child { background:linear-gradient(105deg, #111 0%, #111 54%, #9b6a2f 120%); -webkit-background-clip:text; background-clip:text; color:transparent; }
.home .hero h1 span:last-child { background:linear-gradient(100deg, #111827 0%, #3B82F6 46%, #8B5CF6 100%); -webkit-background-clip:text; background-clip:text; color:transparent; }
.hero p { max-width:620px; color:#171717; font-size:17px; line-height:1.95; font-weight:650; }
.home .hero p { max-width:590px; color:#1f2937; font-size:16.5px; line-height:1.9; font-weight:720; }
.home .hero-lead strong { color:#1e3a8a; font-weight:900; }
.hero-meta { display:flex; flex-wrap:wrap; gap:8px 14px; margin-top:18px; color:#3d3933; font-family:var(--mono); font-size:12px; font-weight:900; letter-spacing:.03em; }
.hero-meta span { padding-top:8px; border-top:1px solid rgba(17,17,17,.22); }
.hero-topic-row { display:inline-flex; align-items:center; gap:12px; margin-top:18px; padding:10px 12px; border:1px solid rgba(17,17,17,.16); background:rgba(255,253,247,.78); }
.home .hero-topic-row { border-color:rgba(59,130,246,.2); background:rgba(255,255,255,.74); box-shadow:0 14px 36px rgba(59,130,246,.08); backdrop-filter:blur(14px); }
.hero-topic-row span { color:var(--accent2); font-family:var(--mono); font-size:12px; font-weight:900; letter-spacing:.1em; text-transform:uppercase; }
.home .hero-topic-row span { color:#3B82F6; }
.hero-topic-row b { font-size:14px; }
.hero-actions { display:flex; gap:12px; flex-wrap:wrap; margin-top:24px; }
.button { position:relative; display:inline-flex; align-items:center; justify-content:center; gap:8px; min-height:44px; padding:11px 18px; border-radius:999px; background:var(--accent); color:#fff; text-decoration:none; font-weight:900; overflow:hidden; box-shadow:0 12px 32px rgba(17,17,17,.16); transition: transform .22s ease, box-shadow .22s ease; }
.home .button { border-radius:999px; background:linear-gradient(100deg, #111827, #2563eb); box-shadow:0 18px 46px rgba(37,99,235,.2); }
.button::before { content:""; position:absolute; inset:0; background:linear-gradient(110deg, transparent 0%, rgba(255,255,255,.25) 45%, transparent 62%); transform:translateX(-120%); transition:transform .75s ease; }
.button:hover { transform:translateY(-2px); box-shadow:0 18px 40px rgba(17,17,17,.2); }
.button:hover::before { transform:translateX(120%); }
.button-secondary { background:transparent; color:var(--accent); border:1px solid rgba(17,17,17,.28); box-shadow:none; }
.home .hero-actions .button-secondary { color:#fff; }
.hero-showcase { display:grid; gap:14px; align-self:stretch; }
.hero-feature-card { position:relative; display:flex; min-height:330px; flex-direction:column; justify-content:space-between; padding:22px; border:1px solid rgba(17,17,17,.2); background:#111; color:#fff; text-decoration:none; overflow:hidden; box-shadow:var(--shadow); }
.home .hero-feature-card { min-height:370px; padding:24px; border:1px solid rgba(59,130,246,.18); border-radius:28px; background:linear-gradient(145deg, rgba(255,255,255,.94), rgba(239,246,255,.88)); color:#111827; box-shadow:0 28px 80px rgba(59,130,246,.18); }
.hero-feature-card::before { content:""; position:absolute; inset:0; background:radial-gradient(circle at 82% 22%, rgba(241,205,141,.2), transparent 28%); pointer-events:none; }
.home .hero-feature-card::before { background:
  radial-gradient(circle at 78% 12%, rgba(139,92,246,.24), transparent 24%),
  radial-gradient(circle at 14% 86%, rgba(59,130,246,.22), transparent 28%); }
.hero-feature-card > * { position:relative; z-index:1; }
.hero-feature-card span { color:#f1cd8d; font-family:var(--mono); font-size:12px; font-weight:900; letter-spacing:.16em; text-transform:uppercase; }
.home .hero-feature-card span { color:#3B82F6; }
.hero-feature-card strong { display:block; margin:12px 0 8px; font-family:var(--display); font-size:40px; line-height:1; letter-spacing:-.055em; }
.home .hero-feature-card strong { font-size:42px; color:#111827; }
.hero-feature-card p { max-width:330px; color:#fff8e9; font-size:15px; font-weight:850; line-height:1.7; }
.home .hero-feature-card p { color:#374151; }
.home .hero-feature-trend { min-height:440px; gap:12px; justify-content:flex-start; }
.hero-feature-heading strong { margin-bottom:0; font-size:clamp(27px,3vw,38px); line-height:1.08; }
.hero-trend-hook, .hero-why-highlight { width:100%; padding:12px 14px; border-radius:17px; background:rgba(255,255,255,.78); border:1px solid rgba(59,130,246,.15); }
.hero-trend-hook b, .hero-why-highlight b { display:block; margin-bottom:4px; color:#2563eb; font-family:var(--mono); font-size:11px; font-weight:900; letter-spacing:.08em; }
.hero-trend-hook p, .hero-why-highlight p { max-width:none; margin:0; font-size:13px; line-height:1.55; }
.hero-why-highlight { background:linear-gradient(135deg,#eff6ff,#f5f3ff); border-width:2px; }
.hero-why-highlight b { color:#6d28d9; }
.hero-product-focus { display:grid; grid-template-columns:128px minmax(0,1fr); gap:14px; align-items:center; width:100%; margin-top:auto; padding:10px 12px; border-radius:17px; background:#fff; border:1px solid rgba(59,130,246,.14); }
.hero-product-focus img { width:128px; height:104px; object-fit:contain; border-radius:12px; background:#f8fafc; }
.hero-product-focus small { color:#334155; font-family:var(--mono); font-size:11px; font-weight:900; line-height:1.6; }
.hero-related-note { color:#6b7280; font-size:10px; font-weight:800; }
.hero-product-stack { display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; margin-top:16px; }
.hero-product-stack img { width:100%; height:120px; object-fit:contain; padding:10px; background:#fffaf0; border:1px solid rgba(255,255,255,.18); filter:drop-shadow(0 12px 16px rgba(0,0,0,.22)); }
.home .hero-product-stack img { height:128px; border-radius:20px; background:rgba(255,255,255,.86); border-color:rgba(59,130,246,.14); filter:drop-shadow(0 16px 18px rgba(37,99,235,.14)); }
.hero-notes { display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; }
.hero-notes a { display:block; padding:13px; border:1px solid rgba(17,17,17,.16); background:#fffdf7; color:var(--ink); text-decoration:none; transition:transform .2s ease, box-shadow .2s ease, border-color .2s ease; }
.hero-notes a:hover { transform:translateY(-2px); border-color:rgba(59,130,246,.34); box-shadow:0 18px 42px rgba(59,130,246,.12); }
.home .hero-notes a { border-radius:18px; border-color:rgba(59,130,246,.14); background:rgba(255,255,255,.82); box-shadow:0 14px 36px rgba(17,24,39,.06); }
.hero-notes b { display:block; color:var(--accent2); font-family:var(--mono); font-size:12px; letter-spacing:.12em; }
.home .hero-notes b { color:#8B5CF6; }
.hero-notes span { display:block; margin-top:4px; font-weight:900; font-size:13px; line-height:1.45; }
.hero-panel { position:relative; padding:18px; border:1px solid rgba(17,17,17,.22); border-radius:0; background:
  linear-gradient(145deg, rgba(255,253,247,.96), rgba(245,241,232,.9)),
  repeating-linear-gradient(0deg, rgba(17,17,17,.045) 0 1px, transparent 1px 12px); box-shadow:var(--shadow); animation:none; overflow:hidden; }
.hero-panel::before { content:"選定中"; position:absolute; right:18px; top:16px; z-index:1; font-family:var(--mono); font-size:11px; letter-spacing:.14em; color:var(--accent2); text-transform:uppercase; }
.hero-panel::after { content:""; position:absolute; left:18px; right:18px; bottom:18px; height:1px; background:rgba(17,17,17,.18); }
.score-card { position:relative; padding:24px; border-radius:0; color:#fff; background:#111; min-height:188px; box-shadow:none; }
.score-card span { color:#f1cd8d; font-family:var(--mono); font-size:12px; text-transform:uppercase; letter-spacing:.16em; font-weight:900; }
.score-card strong { display:block; margin-top:18px; font-family:var(--display); font-size:36px; line-height:1.08; letter-spacing:-.045em; font-weight:900; }
.score-card p { color:#fff8e9; margin-top:16px; font-size:15px; font-weight:800; }
.mini-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:14px; }
.mini-grid div { padding:14px; border:1px solid rgba(17,17,17,.15); border-radius:0; background:rgba(255,255,255,.68); }
.mini-grid b, .mini-grid small { display:block; }
.mini-grid small { color:var(--muted); }
.trust-strip { display:grid; grid-template-columns:repeat(3,1fr); gap:0; margin:0 0 40px; border:1px solid rgba(17,17,17,.18); border-left:0; background:rgba(255,250,240,.78); }
.home .trust-strip { margin-top:-4px; border-color:rgba(59,130,246,.14); background:rgba(255,255,255,.66); box-shadow:0 18px 50px rgba(59,130,246,.07); }
.trust-strip span { padding:14px 16px; border-left:1px solid rgba(17,17,17,.18); color:#3d3933; font-weight:800; text-align:center; }
.home .trust-strip span { display:flex; align-items:center; justify-content:center; gap:8px; flex-wrap:wrap; padding:13px 16px; text-align:left; }
.home .trust-strip b { color:#111827; font-family:var(--display); font-size:17px; line-height:1; letter-spacing:-.03em; }
.home .trust-strip small { color:#3B82F6; font-family:var(--mono); font-size:12px; font-weight:900; letter-spacing:.03em; }
.comparison-index, .page-card { position:relative; padding:28px; border:1px solid rgba(17,17,17,.18); border-radius:0; background:rgba(255,253,247,.9); box-shadow:var(--shadow); overflow:hidden; }
.home .comparison-index { border-color:rgba(59,130,246,.14); border-radius:30px; background:rgba(255,255,255,.76); backdrop-filter:blur(18px); box-shadow:0 26px 80px rgba(17,24,39,.08); }
.page-card::before { content:""; }
.page-card > * { position:relative; }
.home .page-card { display:none; }
.comparison-index h2, .offer-section h2 { margin:8px 0 10px; font-size: clamp(28px, 4vw, 42px); line-height:1.12; letter-spacing:-.05em; }
.section-lead { max-width:880px; color:var(--muted); }
.category-hero { display:block; margin:0 0 20px; padding:28px; border:1px solid rgba(59,130,246,.16); border-radius:28px; background:
  radial-gradient(circle at 82% 12%, rgba(139,92,246,.16), transparent 28%),
  linear-gradient(145deg, rgba(255,255,255,.94), rgba(239,246,255,.86)); color:#111827; box-shadow:0 22px 68px rgba(59,130,246,.12); }
.category-hero h1 { display:block; margin:8px 0 12px; color:#111827; font-size:clamp(42px, 5vw, 62px); line-height:.95; white-space:normal; }
.category-hero h1::after { content:none; }
.category-hero p { max-width:600px; color:#374151; font-size:15.5px; font-weight:760; line-height:1.7; margin:0; }
.category-hero aside { display:flex; flex-direction:column; justify-content:center; padding:18px; border:1px solid rgba(59,130,246,.16); border-radius:22px; background:rgba(255,255,255,.72); }
.category-hero aside span, .category-hero aside small { color:#3B82F6; font-family:var(--mono); font-weight:900; letter-spacing:.12em; text-transform:uppercase; }
.category-hero aside strong { display:block; margin:10px 0; color:#111827; font-family:var(--display); font-size:54px; line-height:1; letter-spacing:-.06em; }
.category-comparison-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); gap:14px; margin:0 0 26px; }
.category-comparison-card { display:flex; flex-direction:column; min-height:198px; padding:18px; border:1px solid rgba(59,130,246,.14); border-radius:22px; background:rgba(255,255,255,.82); color:var(--ink); text-decoration:none; transition:transform .22s ease, box-shadow .22s ease, border-color .22s ease; overflow:hidden; box-shadow:0 14px 42px rgba(17,24,39,.05); }
.category-comparison-card:hover { transform:translateY(-3px); border-color:rgba(17,17,17,.38); box-shadow:0 18px 44px rgba(17,17,17,.1); }
.category-comparison-card span, .category-comparison-card small { color:var(--accent2); font-family:var(--mono); font-size:12px; font-weight:900; letter-spacing:.1em; text-transform:uppercase; }
.category-comparison-card h2 { display:block; margin:12px 0 10px; padding:0; border:0; font-size:clamp(25px, 2.35vw, 31px); line-height:1.08; letter-spacing:-.045em; overflow-wrap:anywhere; }
.category-comparison-card h2::before, .category-comparison-card h2::after { content:none; }
.category-comparison-card p { color:#222; font-weight:780; line-height:1.68; margin:0 0 12px; }
.category-comparison-card small { margin-top:auto; line-height:1.55; }
.category-playbook { display:grid; grid-template-columns:260px minmax(0, 1fr); gap:20px; align-items:start; margin:8px 0 22px; padding:20px; border:1px solid rgba(59,130,246,.14); border-radius:26px; background:rgba(255,255,255,.76); box-shadow:0 18px 54px rgba(17,24,39,.06); }
.category-playbook h2 { display:block; margin:8px 0 8px; padding:0; border:0; font-size:clamp(23px, 2vw, 28px); line-height:1.12; letter-spacing:-.035em; }
.category-next h2 { display:block; margin:8px 0 0; padding:0; border:0; font-size:clamp(28px, 3vw, 38px); line-height:1.05; }
.category-playbook h2::before, .category-playbook h2::after, .category-next h2::before, .category-next h2::after { content:none; }
.category-playbook > div > p { margin:0; color:var(--muted); font-size:13.5px; line-height:1.65; font-weight:750; }
.category-playbook ul { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:12px; margin:0; padding:0; list-style:none; }
.category-playbook li { margin:0; padding:14px; border:1px solid rgba(59,130,246,.12); border-radius:18px; background:linear-gradient(145deg, #ffffff, #f8fbff); }
.category-playbook b { display:block; margin-bottom:7px; font-family:var(--display); font-size:20px; line-height:1.12; letter-spacing:-.04em; }
.category-playbook span { display:block; color:#403b34; font-size:13.5px; line-height:1.68; font-weight:750; }
.category-product-shelf { margin:26px 0 28px; padding:22px; border:1px solid rgba(59,130,246,.14); border-radius:28px; background:linear-gradient(145deg, rgba(255,255,255,.94), rgba(239,246,255,.66)); box-shadow:0 20px 56px rgba(37,99,235,.08); }
.category-product-shelf h2 { display:block; margin:6px 0 8px; padding:0; border:0; font-size:clamp(30px, 4vw, 44px); line-height:1.05; letter-spacing:-.055em; }
.category-product-shelf h2::before, .category-product-shelf h2::after { content:none; }
.category-product-shelf > p { max-width:760px; margin:0 0 16px; color:#4b5563; font-weight:800; line-height:1.8; }
.category-product-grid { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:14px; }
.category-product-card { display:grid; grid-template-columns:148px minmax(0, 1fr); gap:16px; align-items:start; min-height:270px; padding:16px; border:1px solid rgba(59,130,246,.14); border-radius:22px; background:#fff; box-shadow:0 12px 34px rgba(17,24,39,.05); }
.category-product-image { display:block; text-decoration:none; }
.category-product-image .offer-visual { height:118px; margin:0; }
.category-product-signal { display:inline-flex; align-items:center; gap:7px; width:max-content; max-width:100%; margin:0 0 8px; padding:5px 9px; border-radius:999px; background:#f1f5f9; color:#475569; }
.category-product-signal b { font-family:var(--mono); font-size:11px; letter-spacing:.05em; }
.category-product-signal small { display:inline; color:inherit; font-size:10px; font-weight:850; }
.category-product-signal.signal-trending { background:linear-gradient(100deg,#ede9fe,#fdf2f8); color:#6d28d9; border:1px solid rgba(109,40,217,.2); box-shadow:0 6px 18px rgba(109,40,217,.1); }
.category-product-signal.signal-reviews { background:#eff6ff; color:#1d4ed8; }
.category-product-signal.signal-purpose { background:#ecfdf5; color:#047857; }
.category-product-card span { display:block; color:var(--accent2); font-family:var(--mono); font-size:11px; font-weight:900; letter-spacing:.1em; text-transform:uppercase; }
.category-product-card h3 { display:block; margin:7px 0 8px; padding:0; border:0; font-size:20px; line-height:1.2; letter-spacing:-.035em; }
.category-product-card h3::before, .category-product-card h3::after { content:none; }
.category-product-card p { margin:0 0 8px; color:#374151; font-weight:800; line-height:1.6; }
.category-product-intro { font-size:14px; }
.category-trend-reason { margin:10px 0 12px; padding:10px 11px; border:1px solid rgba(109,40,217,.18); border-left:4px solid #7c3aed; border-radius:0 13px 13px 0; background:linear-gradient(135deg,#f5f3ff,#fdf2f8); }
.category-trend-reason b { display:block; margin-bottom:3px; color:#6d28d9; font-family:var(--mono); font-size:11px; letter-spacing:.06em; }
.category-trend-reason p { margin:0; color:#374151; font-size:12px; line-height:1.55; }
.category-trend-reason small { margin-top:5px; color:#6b7280; font-size:10px; }
.category-product-reasons { display:grid; gap:6px; margin:12px 0; }
.category-product-reasons p { display:grid; grid-template-columns:92px minmax(0, 1fr); gap:8px; margin:0; padding:8px 10px; border-radius:12px; background:#f7f9ff; color:#4b5563; font-size:12px; font-weight:700; line-height:1.5; }
.category-product-reasons b { color:#1d4ed8; font-family:var(--mono); font-size:11px; letter-spacing:.03em; }
.category-product-card small { display:block; color:var(--muted); font-family:var(--mono); font-size:12px; line-height:1.45; }
.category-product-actions { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-top:12px; }
.category-product-actions .button { min-height:38px; padding:8px 13px; font-size:13px; }
.category-guide-link { color:#2563eb; font-weight:900; text-decoration:none; font-size:13px; }
.category-guide-link:hover { text-decoration:underline; }
.home-trend-pulse { margin:18px 0 30px; padding:22px; border:1px solid rgba(59,130,246,.18); border-radius:28px; background:linear-gradient(135deg,rgba(239,246,255,.96),rgba(250,245,255,.94)); box-shadow:0 20px 54px rgba(37,99,235,.08); }
.home-trend-pulse > div:first-child { display:flex; align-items:end; justify-content:space-between; gap:18px; margin-bottom:15px; }
.home-trend-pulse > div:first-child span { color:#2563eb; font-family:var(--mono); font-size:12px; font-weight:900; letter-spacing:.1em; }
.home-trend-pulse h2 { margin:0; padding:0; border:0; font-size:clamp(27px,3.5vw,39px); }
.home-trend-pulse h2::before, .home-trend-pulse h2::after { content:none; }
.home-trend-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
.home-trend-card { display:grid; grid-template-columns:104px minmax(0,1fr); gap:13px; min-height:230px; padding:14px; border:1px solid rgba(59,130,246,.16); border-radius:20px; background:rgba(255,255,255,.9); color:#111827; text-decoration:none; }
.home-trend-card img { width:104px; height:128px; object-fit:contain; border-radius:13px; background:#f8fafc; }
.home-trend-card span { display:block; color:#2563eb; font-family:var(--mono); font-size:10px; font-weight:900; }
.home-trend-card strong { display:block; margin:6px 0 10px; font-family:var(--display); font-size:19px; line-height:1.22; }
.home-trend-card p { margin:7px 0 0; padding:8px 9px; border-radius:11px; color:#4b5563; font-size:11px; font-weight:750; line-height:1.5; }
.home-trend-card p b { display:block; margin-bottom:3px; color:#1d4ed8; font-family:var(--mono); font-size:10px; letter-spacing:.04em; }
.home-trend-trigger { background:#f8fafc; }
.home-trend-reason { background:#eff6ff; border-left:3px solid #3b82f6; }
.trend-evidence { margin:22px 0 26px; padding:22px; border:1px solid rgba(139,92,246,.2); border-radius:28px; background:linear-gradient(145deg, rgba(248,250,255,.98), rgba(245,243,255,.9)); box-shadow:0 20px 54px rgba(76,29,149,.08); }
.trend-evidence > h2 { display:block; margin:7px 0 8px; padding:0; border:0; font-size:clamp(30px,4vw,43px); letter-spacing:-.055em; }
.trend-evidence > h2::before, .trend-evidence > h2::after { content:none; }
.trend-evidence-lead { margin:0 0 16px; color:#4b5563; font-weight:750; }
.trend-evidence-card { padding:18px; border:1px solid rgba(59,130,246,.16); border-radius:22px; background:rgba(255,255,255,.88); }
.trend-evidence-card + .trend-evidence-card { margin-top:12px; }
.trend-badges { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
.trend-badges span, .trend-badges b, .trend-badges small { display:inline-flex; padding:5px 9px; border-radius:999px; background:#eff6ff; color:#1d4ed8; font-family:var(--mono); font-size:11px; font-weight:800; letter-spacing:.04em; }
.trend-badges b { background:#ede9fe; color:#6d28d9; }
.trend-badges small { background:#f3f4f6; color:#6b7280; }
.trend-evidence-card h2 { display:block; margin:12px 0 8px; padding:0; border:0; font-size:clamp(23px,3vw,31px); line-height:1.18; letter-spacing:-.04em; }
.trend-evidence-card h2::before, .trend-evidence-card h2::after { content:none; }
.trend-why { margin:0 0 10px; color:#374151; font-weight:760; line-height:1.75; }
.trend-audience { margin:0 0 14px; color:#111827; }
.trend-audience b { display:inline-block; margin-right:9px; color:#2563eb; }
.trend-product-mini { display:grid; grid-template-columns:132px minmax(0,1fr); gap:16px; align-items:center; padding:14px; border-radius:18px; background:#fff; border:1px solid rgba(59,130,246,.13); }
.trend-product-mini > div { display:grid; place-items:center; height:116px; border-radius:14px; background:#f8fafc; }
.trend-product-mini img { max-width:100%; max-height:108px; object-fit:contain; }
.trend-product-mini p { margin:0; }
.trend-product-mini strong { display:block; font-family:var(--display); font-size:21px; line-height:1.25; }
.trend-product-mini small { display:block; margin-top:8px; color:#6b7280; font-weight:800; }
.trend-actions { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-top:14px; }
.trend-source-link { color:#2563eb; font-weight:900; }
.trend-disclaimer { display:block; margin-top:12px; color:#6b7280; line-height:1.6; }
.category-next { margin:0 0 6px; padding:20px 0 0; border-top:2px solid rgba(17,17,17,.72); }
.category-next div:last-child { display:flex; flex-wrap:wrap; gap:9px; margin-top:14px; }
.category-next span { display:inline-flex; padding:7px 11px; border:1px solid rgba(17,17,17,.16); background:#fff; color:#2c2924; font-weight:850; }
.related-guides { margin:42px 0 0; padding:24px; border:1px solid rgba(59,130,246,.14); border-radius:26px; background:linear-gradient(145deg, #fff, #f8fbff); }
.related-guides h2 { margin-top:8px; }
.related-guides > div:last-child { display:grid; grid-template-columns:repeat(auto-fit, minmax(210px, 1fr)); gap:12px; }
.related-guides a { display:flex; min-height:128px; flex-direction:column; padding:16px; border:1px solid rgba(59,130,246,.14); border-radius:18px; background:#fff; color:#111827; text-decoration:none; }
.related-guides a span, .related-guides a small { color:#2563eb; font-family:var(--mono); font-size:11px; font-weight:900; letter-spacing:.08em; text-transform:uppercase; }
.related-guides a strong { margin:8px 0; font-family:var(--display); font-size:22px; line-height:1.15; }
.related-guides a small { margin-top:auto; color:#6b7280; }
.article-grid { display:grid; grid-template-columns: repeat(3, 1fr); gap:12px; margin-top:22px; }
.home .article-grid { grid-template-columns:repeat(3, minmax(0, 1fr)); align-items:stretch; gap:14px; }
.article-card { min-height:230px; padding:16px; border-radius:0; background:#fff; border:1px solid rgba(17,17,17,.16); text-decoration:none; color:var(--ink); transition:transform .22s ease, box-shadow .22s ease, border-color .22s ease; overflow:hidden; }
.home .article-card { border-radius:24px; border-color:rgba(59,130,246,.14); background:rgba(255,255,255,.82); box-shadow:0 14px 42px rgba(17,24,39,.06); }
.article-card.featured { grid-column:span 2; background:#111; color:#fff; }
.home .article-card.featured { background:linear-gradient(145deg, #111827, #1e3a8a); }
.article-card:hover { transform:translateY(-3px); border-color:rgba(17,17,17,.38); box-shadow:0 18px 46px rgba(17,17,17,.1); }
.article-card figure { height:120px; margin:0 0 14px; display:grid; place-items:center; border:1px solid rgba(17,17,17,.12); background:#fffaf0; overflow:hidden; }
.home .article-card figure { height:132px; }
.home .article-card figure { border-radius:18px; border-color:rgba(59,130,246,.12); background:linear-gradient(145deg, #eff6ff, #faf5ff); }
.article-card.featured figure { background:#fffaf0; border-color:rgba(255,255,255,.16); }
.article-card figure img { max-width:100%; max-height:104px; object-fit:contain; filter:drop-shadow(0 12px 16px rgba(20,16,12,.12)); }
.article-card .figure-mark { color:#111; font-family:var(--display); font-size:34px; font-weight:900; letter-spacing:-.05em; }
.article-card span { font-family:var(--mono); color:var(--accent2); font-size:12px; font-weight:900; text-transform:uppercase; letter-spacing:.14em; }
.article-card h3 { display:block; margin:12px 0 8px; padding:0; border-radius:0; background:none; color:inherit; font-family:var(--display); font-size:25px; line-height:1.18; letter-spacing:-.04em; }
.article-card h3::before { content:none; }
.article-card p { color:inherit; opacity:.78; }
.home .article-card h3 { font-size:23px; min-height:56px; }
.home .article-card p { min-height:58px; font-size:14px; line-height:1.7; }
h1 { position:relative; display:inline-block; max-width:100%; font-family:var(--display); font-size: clamp(34px, 3.55vw, 45px); line-height:1.06; letter-spacing:-.065em; margin: 10px 0 24px; color:var(--ink); text-wrap:balance; }
.subpage h1 { padding-right:8px; background:none; color:var(--ink); }
.subpage h1::after { content:""; position:absolute; left:0; right:0; bottom:-10px; height:2px; background:linear-gradient(90deg, #111 0 38%, rgba(155,106,47,.65) 38% 62%, transparent 62%); z-index:-1; }
.subpage .category-hero h1 { color:#111827; padding-right:0; }
.subpage .comparison-hero h1 { color:#111827; padding-right:0; }
.subpage .category-hero h1::after, .subpage .comparison-hero h1::after { content:none; }
@media (min-width: 900px) {
  .subpage h1 { white-space:nowrap; }
}
h2 { position:relative; display:flex; align-items:center; gap:12px; margin-top: 38px; border-top:2px solid rgba(17,17,17,.72); padding-top:18px; font-family:var(--display); font-size:32px; line-height:1.15; letter-spacing:-.04em; color:var(--ink); }
h2::before { content:"§"; flex:0 0 auto; width:auto; height:auto; border-radius:0; background:none; box-shadow:none; color:var(--accent2); font-family:var(--display); font-size:28px; line-height:1; }
h2::after { content:""; flex:1 1 auto; height:1px; min-width:32px; background:rgba(17,17,17,.18); transform:translateY(3px); }
h3 { position:relative; display:inline-flex; align-items:center; gap:8px; margin:20px 0 8px; padding:0 0 4px; border-radius:0; border-bottom:1px solid rgba(155,106,47,.42); background:none; color:var(--ink); font-weight:900; letter-spacing:-.02em; }
h3::before { content:""; width:8px; height:8px; border-radius:0; background:var(--accent2); box-shadow:none; transform:rotate(45deg); }
p, li { font-size: 15.8px; }
.page-card > p, .page-card > ul, .page-card > ol { max-width:980px; }
.page-card p { margin:10px 0; }
.page-card ul, .page-card ol { margin-top:10px; margin-bottom:14px; }
.comparison-hero { position:relative; display:grid; grid-template-columns:minmax(0, 1.2fr) minmax(280px, .8fr); gap:24px; align-items:stretch; margin:-6px 0 28px; padding:28px; border:1px solid rgba(59,130,246,.16); border-radius:30px; background:
  radial-gradient(circle at 82% 14%, rgba(139,92,246,.16), transparent 28%),
  linear-gradient(145deg, rgba(255,255,255,.96), rgba(239,246,255,.88)); color:#111827; overflow:hidden; box-shadow:0 24px 76px rgba(59,130,246,.12); }
.comparison-hero::before { content:"選び方ガイド"; position:absolute; right:18px; top:18px; font-family:var(--mono); font-size:12px; line-height:1; letter-spacing:.12em; color:rgba(59,130,246,.28); pointer-events:none; }
.comparison-hero-copy { position:relative; z-index:1; display:flex; flex-direction:column; justify-content:center; min-height:290px; }
.comparison-hero .section-kicker { color:#3B82F6; }
.comparison-hero h1 { display:block; max-width:780px; margin:16px 0 16px; color:#111827; font-size:clamp(38px, 4.6vw, 58px); line-height:.98; letter-spacing:-.07em; text-wrap:balance; white-space:normal; }
.comparison-hero h1::after { content:none; }
.comparison-title-sub { margin:-6px 0 14px; color:#3B82F6; font-family:var(--display); font-size:clamp(24px, 2.5vw, 34px); font-weight:900; line-height:1.18; letter-spacing:-.045em; }
.comparison-hero p { max-width:760px; color:#374151; font-size:16px; font-weight:750; line-height:1.9; }
.comparison-hero-actions { display:flex; gap:12px; flex-wrap:wrap; margin-top:18px; }
.comparison-hero .button-primary { background:linear-gradient(100deg, #111827, #2563eb); color:#fff; }
.comparison-hero .button-secondary { color:#111827; border-color:rgba(59,130,246,.24); background:rgba(255,255,255,.62); }
.comparison-hero-panel { position:relative; z-index:1; display:flex; flex-direction:column; justify-content:space-between; gap:16px; padding:20px; border:1px solid rgba(59,130,246,.16); border-radius:24px; background:rgba(255,255,255,.72); backdrop-filter:blur(10px); }
.comparison-hero-products strong { font-size:32px; }
.comparison-preview-list { display:grid; gap:10px; }
.comparison-preview-list a { display:grid; grid-template-columns:64px minmax(0, 1fr); gap:10px; align-items:center; min-height:74px; padding:8px; border:1px solid rgba(59,130,246,.14); border-radius:18px; background:rgba(255,255,255,.84); color:#111827; text-decoration:none; transition:transform .2s ease, box-shadow .2s ease, border-color .2s ease; }
.comparison-preview-list a:hover { transform:translateY(-2px); border-color:rgba(59,130,246,.34); box-shadow:0 14px 34px rgba(59,130,246,.12); }
.comparison-preview-list img { grid-column:1; grid-row:1; width:64px; height:58px; object-fit:contain; padding:5px; border-radius:14px; background:linear-gradient(145deg, #eff6ff, #faf5ff); }
.comparison-preview-list span { grid-column:2; font-family:var(--display); font-size:19px; font-weight:900; line-height:1.1; letter-spacing:-.04em; }
.comparison-preview-list a:not(:has(img)) { grid-template-columns:1fr; }
.comparison-panel-label { margin:0; color:#3B82F6; font-family:var(--mono); font-size:12px; font-weight:900; letter-spacing:.16em; text-transform:uppercase; }
.comparison-hero-panel strong { display:block; font-family:var(--display); font-size:40px; line-height:1; letter-spacing:-.06em; color:#111827; }
.comparison-panel-metrics { display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; }
.comparison-panel-metrics span { padding:10px; border:1px solid rgba(59,130,246,.14); border-radius:16px; background:rgba(255,255,255,.76); }
.comparison-panel-metrics b, .comparison-panel-metrics small { display:block; }
.comparison-panel-metrics b { color:#111827; font-size:16px; }
.comparison-panel-metrics small { color:#3B82F6; font-size:11px; font-family:var(--mono); }
.comparison-chips, .comparison-point-chips { display:flex; flex-wrap:wrap; gap:8px; }
.comparison-chips span, .comparison-point-chips span { display:inline-flex; align-items:center; min-height:34px; padding:6px 10px; border:1px solid rgba(59,130,246,.16); border-radius:999px; background:rgba(255,255,255,.72); color:#111827; font-weight:850; font-size:13px; }
.comparison-axis { margin:0 0 30px; padding:22px; border:1px solid rgba(59,130,246,.14); border-radius:26px; background:rgba(255,255,255,.76); box-shadow:0 18px 54px rgba(17,24,39,.06); }
.comparison-axis h2 { margin-top:8px; }
.comparison-axis .comparison-point-chips span { border-color:rgba(59,130,246,.16); background:#eff6ff; color:#1e3a8a; font-family:var(--mono); font-size:12px; letter-spacing:.03em; }
.comparison-axis-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(210px, 1fr)); gap:12px; margin-top:18px; }
.comparison-axis-card { padding:16px; border:1px solid rgba(59,130,246,.12); border-radius:20px; background:#fff; box-shadow:0 12px 28px rgba(17,24,39,.05); }
.comparison-axis-card > span { color:var(--accent2); font-family:var(--mono); font-size:12px; font-weight:900; letter-spacing:.12em; }
.comparison-axis-card h3 { display:block; margin:9px 0 8px; font-family:var(--display); font-size:22px; line-height:1.15; border:0; }
.comparison-axis-card h3::before { content:none; }
.comparison-axis-card p { margin:0 0 10px; color:#222; font-weight:800; line-height:1.7; }
.comparison-axis-card small { display:block; color:var(--muted); font-family:var(--mono); font-size:12px; line-height:1.55; }
.notice, .ad-label { background:#fff8e6; border:1px solid #d9bf83; color:#5c430c; padding:10px 14px; border-radius:0; font-size:14px; }
.table-wrap { overflow-x:auto; margin: 18px 0; border-radius:18px; box-shadow:none; border:1px solid rgba(59,130,246,.14); }
table { width:100%; min-width:760px; border-collapse: collapse; background:#fff; overflow:hidden; }
th, td { border-bottom:1px solid rgba(17,17,17,.12); padding:12px; text-align:left; vertical-align:top; word-break:auto-phrase; overflow-wrap:normal; }
th:first-child, td:first-child { white-space:nowrap; }
th { background:#eff6ff; color:#1e3a8a; font-family:var(--mono); font-size:12px; letter-spacing:.04em; }
.offer-compare-wrap { margin:22px 0 20px; border-width:2px; }
.offer-compare-table td:first-child { min-width:150px; font-family:var(--display); font-size:18px; line-height:1.45; }
.offer-compare-table b { color:var(--accent2); font-family:var(--mono); font-size:12px; letter-spacing:.1em; }
.status-pill { display:inline-flex; min-width:62px; justify-content:center; padding:4px 8px; border:1px solid rgba(17,17,17,.16); font-size:12px; font-weight:900; }
.status-active { background:#2563eb; color:#fff; border-color:#2563eb; }
.status-pending { background:#f1f1f1; color:#60594f; }
.offer-section { margin-top:38px; }
.offer-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:14px; margin-top:16px; }
.offer-table-wrap { margin-top:28px; }
.offer-card { position:relative; background:#fff; border:1px solid rgba(59,130,246,.14); border-radius:22px; padding:14px 16px 16px; box-shadow:0 14px 42px rgba(17,24,39,.05); transition:transform .22s ease, box-shadow .22s ease, border-color .22s ease; overflow:hidden; }
.offer-card:hover { transform:translateY(-3px); border-color:rgba(17,17,17,.38); box-shadow:0 18px 42px rgba(17,17,17,.1); }
.offer-card::before { content:""; }
.offer-rank { display:inline-flex; margin:0 0 10px; padding:3px 8px; border-radius:999px; background:#eff6ff; color:#2563eb; font-family:var(--mono); font-size:12px; font-weight:900; letter-spacing:.1em; }
.offer-visual { height:132px; margin:0 -2px 12px; display:grid; place-items:center; border-radius:18px; background:linear-gradient(145deg, #eff6ff, #faf5ff); border:1px solid rgba(59,130,246,.12); overflow:hidden; }
.offer-visual img { max-width:100%; max-height:116px; object-fit:contain; filter: drop-shadow(0 14px 18px rgba(40,32,18,.14)); transition:transform .28s ease; }
.offer-card:hover .offer-visual img { transform:scale(1.035) rotate(-1deg); }
.offer-visual-fallback span { width:92px; height:92px; border-radius:999px; display:grid; place-items:center; background:var(--accent); color:#fff; font-weight:900; }
.offer-label { font-family:var(--mono); color:var(--accent2); font-size:11px; letter-spacing:.12em; font-weight:900; text-transform:uppercase; margin:0 0 7px; }
.offer-name { min-height:5.8em; margin:0 0 10px; overflow:hidden; display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:4; font-family:var(--body); font-weight:800; font-size:15px; line-height:1.45; letter-spacing:0; word-break:break-word; }
.offer-stats { display:flex; flex-wrap:wrap; gap:5px; margin:0 0 8px; }
.offer-stats span { padding:3px 7px; border-radius:0; background:#f1f1f1; color:#333; border:1px solid rgba(17,17,17,.12); font-family:var(--mono); font-size:11px; font-weight:900; }
.offer-problem { color:#4b5563; margin:8px 0; }
.offer-evidence { background:linear-gradient(135deg,#eff6ff,#f8fafc); border:1px solid rgba(37,99,235,.2); border-left:4px solid var(--accent); border-radius:0 14px 14px 0; color:#334155; font-size:13px; line-height:1.6; margin:12px 0; padding:11px 12px; }
.offer-evidence span { color:var(--accent); display:block; font-family:var(--mono); font-size:11px; font-weight:900; letter-spacing:.08em; margin-bottom:5px; }
.offer-evidence strong { display:block; margin-bottom:4px; color:#111827; font-size:14px; line-height:1.4; }
.offer-evidence p { margin:0; color:#334155; font-size:12px; line-height:1.6; }
.offer-evidence small { display:block; margin-top:6px; color:#6b7280; font-size:10px; font-weight:800; }
.offer-evidence-trend { background:linear-gradient(135deg,#eef2ff,#faf5ff); border-color:rgba(109,40,217,.22); border-left-color:#7c3aed; box-shadow:0 8px 22px rgba(109,40,217,.08); }
.offer-evidence-trend span { color:#6d28d9; }
.offer-points { color:var(--muted); font-size:13px; margin:8px 0; }
.offer-points span { display:block; color:var(--accent); font-family:var(--mono); font-weight:900; margin-bottom:3px; }
.offer-card-active { border-color:#dec99f; }
.pending { display:inline-block; padding:4px 10px; border-radius:999px; background:#f1f3f6; color:var(--muted); font-weight:700; }
.offer-meta, .offer-note, footer { color:var(--muted); font-size:13px; }
.editorial-article { max-width:920px; margin:28px auto; }
.category-articles { margin:24px 0; padding:24px; border:1px solid rgba(59,130,246,.16); border-radius:24px; background:rgba(255,255,255,.72); }
.category-articles h2 { margin-top:8px; }
.category-articles > div:last-child { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }
.category-articles a { display:flex; flex-direction:column; gap:8px; min-height:148px; padding:18px; color:var(--ink); text-decoration:none; border:1px solid rgba(59,130,246,.14); border-radius:18px; background:#fff; }
.category-articles a:hover { transform:translateY(-2px); border-color:#3b82f6; }
.category-articles span, .category-articles small { color:#2563eb; font-family:var(--mono); font-size:11px; font-weight:900; letter-spacing:.08em; }
.category-articles strong { font-family:var(--display); font-size:21px; line-height:1.35; }
.editorial-article > h1 { max-width:780px; margin-bottom:28px; }
.editorial-article > p, .editorial-article > ul, .editorial-article > ol { max-width:760px; }
.article-next { display:grid; grid-template-columns:1fr auto; gap:8px 20px; align-items:center; margin-top:38px; padding:22px; border-radius:20px; background:linear-gradient(135deg,#eff6ff,#faf5ff); border:1px solid rgba(59,130,246,.18); }
.article-next span { color:#2563eb; font-family:var(--mono); font-size:12px; font-weight:900; letter-spacing:.12em; }
.article-next strong { grid-column:1; font-family:var(--display); font-size:24px; }
.article-next .button { grid-column:2; grid-row:1 / span 2; }
footer { border-top:1px solid var(--line); width:min(1120px, calc(100% - 32px)); margin:0 auto; padding:28px 0 46px; }
@keyframes rise { from { opacity:0; transform:translateY(18px); } to { opacity:1; transform:none; } }
@keyframes floatIn { from { opacity:0; transform:translateY(20px) scale(.98); } to { opacity:1; transform:none; } }
@media (max-width: 1040px) {
  .home .article-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); }
  .home-trend-grid { grid-template-columns:1fr; }
}
@media (max-width: 820px) {
  .site-header { align-items:flex-start; flex-direction:column; gap:8px; padding:10px 12px 8px; }
  nav { width:100%; gap:6px; flex-wrap:nowrap; justify-content:flex-start; overflow-x:auto; overscroll-behavior-inline:contain; scrollbar-width:none; }
  nav::-webkit-scrollbar { display:none; }
  nav a { flex:0 0 auto; min-height:32px; padding:5px 9px; }
  main { width:min(1120px, calc(100% - 16px)); }
  .hero { grid-template-columns:1fr; min-height:auto; gap:20px; padding:32px 0 22px; }
  .hero h1, .home .hero h1 { max-width:100%; font-size:34px; line-height:1.12; margin:12px 0 14px; letter-spacing:-.045em; word-break:keep-all; overflow-wrap:normal; }
  .hero h1 span { white-space:nowrap; }
  .home .hero-feature-card strong { font-size:32px; line-height:1.08; }
  .home .hero-feature-trend { min-height:0; }
  .hero p { font-size:16px; line-height:1.75; }
  .hero-actions { margin-top:18px; gap:10px; }
  .hero-topic-row { align-items:flex-start; flex-direction:column; gap:4px; }
  .hero-product-stack, .hero-notes { grid-template-columns:1fr; }
  .hero-product-stack img { height:110px; }
  .hero-panel { padding:16px; border-radius:24px; }
  .score-card { min-height:164px; padding:20px; }
  .score-card strong { font-size:27px; }
  .trust-strip, .article-grid, .home .article-grid { grid-template-columns:1fr; }
  .category-hero { grid-template-columns:1fr; padding:20px; }
  .category-hero h1 { font-size:36px; line-height:1.12; word-break:keep-all; }
  .category-hero p { font-size:15px; line-height:1.75; }
  .category-comparison-grid { grid-template-columns:1fr; }
  .category-comparison-card { min-height:0; }
  .category-comparison-card h2 { font-size:25px; overflow-wrap:normal; word-break:keep-all; }
  .category-product-grid { grid-template-columns:1fr; }
  .home-trend-pulse > div:first-child { align-items:flex-start; flex-direction:column; gap:3px; }
  .category-product-card { grid-template-columns:104px minmax(0, 1fr); }
  .category-product-image .offer-visual { height:104px; }
  .category-playbook { grid-template-columns:1fr; padding:18px; }
  .category-playbook ul { grid-template-columns:1fr; }
  .article-card.featured { grid-column:auto; }
  .comparison-index, .page-card { padding:20px; border-radius:22px; }
  .page-card::before { width:190px; height:130px; right:-18px; top:72px; opacity:.68; }
  .comparison-hero { grid-template-columns:1fr; margin:-2px 0 22px; padding:20px; }
  .comparison-hero-copy { min-height:auto; }
  .comparison-hero h1 { font-size:32px; line-height:1.12; word-break:auto-phrase; }
  .comparison-hero-panel { gap:10px; padding:15px; }
  .comparison-hero-panel strong { font-size:26px; line-height:1.1; }
  .comparison-preview-list { gap:7px; }
  .comparison-preview-list a { min-height:62px; }
  .comparison-panel-metrics { grid-template-columns:1fr 1fr 1fr; }
  .comparison-axis { padding:18px; }
  .comparison-axis-grid { grid-template-columns:1fr; }
  h1 { font-size:32px; letter-spacing:-.055em; line-height:1.14; }
  h2 { margin-top:26px; padding-top:16px; font-size:24px; line-height:1.2; gap:8px; }
  h2::before { width:9px; height:28px; }
  h3 { font-size:18px; }
  .offer-grid { grid-template-columns:1fr; }
  .article-next { grid-template-columns:1fr; }
  .article-next .button { grid-column:1; grid-row:auto; }
  .mini-grid { grid-template-columns:1fr 1fr; gap:10px; }
  .mini-grid div { padding:12px; }
}
@media (max-width: 560px) {
  .brand { font-size:18px; }
  .category-hero { margin-bottom:14px; padding:17px; border-radius:22px; }
  .category-hero h1 { margin:6px 0 10px; font-size:33px; }
  .category-hero aside { padding:14px; border-radius:18px; }
  .category-hero aside strong { margin:7px 0; font-size:44px; }
  .category-comparison-grid { gap:10px; margin-bottom:18px; }
  .category-comparison-card { padding:16px; border-radius:18px; }
  .category-comparison-card h2 { margin:9px 0 8px; font-size:23px; line-height:1.16; }
  .category-product-shelf { margin:18px 0; padding:14px; border-radius:22px; }
  .category-product-shelf h2 { font-size:27px; }
  .category-product-card { grid-template-columns:1fr; min-height:0; padding:14px; }
  .category-product-image .offer-visual { height:154px; }
  .category-product-card h3 { font-size:17px; line-height:1.3; }
  .category-product-reasons p { grid-template-columns:82px minmax(0, 1fr); }
  .category-product-actions .button { width:100%; }
  .trend-evidence { margin:16px 0 20px; padding:14px; border-radius:22px; }
  .home-trend-pulse { margin:12px 0 20px; padding:14px; border-radius:22px; }
  .home-trend-pulse h2 { font-size:25px; }
  .home-trend-card { grid-template-columns:82px minmax(0,1fr); min-height:0; padding:10px; border-radius:17px; }
  .home-trend-card img { width:82px; height:100px; }
  .home-trend-card strong { font-size:17px; }
  .hero-product-focus { grid-template-columns:92px minmax(0,1fr); gap:10px; }
  .hero-product-focus img { width:92px; height:82px; }
  .trend-evidence > h2 { font-size:27px; }
  .trend-evidence-card { padding:14px; border-radius:18px; }
  .trend-evidence-card h2 { font-size:21px; }
  .trend-product-mini { grid-template-columns:88px minmax(0,1fr); gap:11px; padding:10px; }
  .trend-product-mini > div { height:88px; }
  .trend-product-mini img { max-height:82px; }
  .trend-product-mini strong { font-size:17px; }
  .trend-actions .button { width:100%; }
  .comparison-index, .page-card { padding:14px; }
  .offer-card { padding:13px; }
  .offer-visual { height:150px; }
  .offer-name { min-height:0; }
  .offer-card .button { width:100%; }
  .table-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation:none !important; transition:none !important; scroll-behavior:auto !important; }
}
"""
