from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from .analytics import add_metric, import_conversions
from .affiliate_performance import import_affiliate_metrics, write_affiliate_performance_report
from .carousel import render_carousel
from .catalog import import_offers, upsert_offer_csv
from .collectors import add_manual_signal, collect_sources, load_sources, upsert_source
from .database import connect, initialize, transaction
from .pipeline import run_pipeline
from .product_scout import activate_candidates, best_by_offer, scout_page_products, write_candidates_csv
from .product_operations import run_product_operations
from .product_expansion import expand_products_from_cache
from .publish_check import check_publish_ready
from .publishing import WordPressPublisher
from .reporting import report_data, write_ceo_report
from .rakuten import RakutenProductClient
from .settings import ensure_directories, load_settings
from .social import (
    add_social_metric, approve_posts, discord_ready_messages, dispatch, export_queue, list_queue,
    import_manual_social_posts, mark_post_published, reject_post, reschedule_post, retry_post, set_media_urls,
    send_discord_ready_messages,
)
from .social_optimization import add_funnel_metric, release_b_variants, write_learning_report
from .static_site import build_static_site
from .trend_screening import enqueue_latest_opportunities, screen_trend_opportunities


def _init() -> None:
    settings = load_settings()
    ensure_directories(settings)
    initialize(settings.database_path)
    print("初期化完了: %s" % settings.database_path)


def _seed() -> None:
    settings = load_settings()
    initialize(settings.database_path)
    count = import_offers(settings)
    with transaction(settings.database_path) as conn:
        for source in load_sources():
            upsert_source(conn, source)
    print("初期データ登録: 商品候補%d件 / 情報源%d件" % (count, len(load_sources())))


def _collect() -> None:
    settings = load_settings()
    initialize(settings.database_path)
    seen, added, errors = collect_sources(settings)
    print("収集完了: 取得%d件 / 新規%d件" % (seen, added))
    for error in errors:
        print("警告: %s" % error, file=sys.stderr)


def _add_signal(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    added = add_manual_signal(settings, args.title, args.url, args.summary, args.category or "")
    print("シグナルを%sしました" % ("追加" if added else "重複として無視"))


def _run(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    counters = run_pipeline(settings, allow_paid=args.allow_paid)
    print(json.dumps(counters, ensure_ascii=False, indent=2))


def _demo() -> None:
    base = load_settings()
    settings = replace(
        base,
        database_path=base.database_path.parent / "trend_commerce_demo.db",
        output_dir=base.output_dir / "demo",
        draft_threshold=0,
    )
    ensure_directories(settings)
    initialize(settings.database_path)
    import_offers(settings)
    demo_sources = [source for source in load_sources() if source.name == "デモ公式フィード"]
    for source in demo_sources:
        source.active = True
    seen, added, errors = collect_sources(settings, demo_sources)
    counters = run_pipeline(settings, allow_paid=False)
    report_path = write_ceo_report(settings)
    result = {"collected": seen, "new": added, "errors": errors, "pipeline": counters, "report": str(report_path)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _report() -> None:
    settings = load_settings()
    initialize(settings.database_path)
    path = write_ceo_report(settings)
    data = report_data(settings)
    print(json.dumps(data["counts"], ensure_ascii=False, indent=2))
    print("レポート: %s" % path)


def _status() -> None:
    settings = load_settings()
    initialize(settings.database_path)
    data = report_data(settings)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _import_conversions(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    result = import_conversions(settings, Path(args.file))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _add_metric(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    add_metric(
        settings, args.content_id, args.measured_at, args.sessions, args.outbound_clicks,
        args.conversions, args.revenue, args.source,
    )
    print("指標を保存しました")


def _review(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    allowed = {"approved", "rejected", "revision_required"}
    if args.decision not in allowed:
        raise SystemExit("decisionは %s のいずれか" % ", ".join(sorted(allowed)))
    with transaction(settings.database_path) as conn:
        row = conn.execute("SELECT id FROM content_items WHERE id=?", (args.content_id,)).fetchone()
        if row is None:
            raise SystemExit("記事IDが見つかりません")
        conn.execute(
            "INSERT INTO human_reviews(object_type, object_id, decision, notes) VALUES ('content', ?, ?, ?)",
            (args.content_id, args.decision, args.notes or ""),
        )
        new_status = "human_approved" if args.decision == "approved" else args.decision
        conn.execute("UPDATE content_items SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (new_status, args.content_id))
    print("レビューを記録しました: content=%d decision=%s" % (args.content_id, args.decision))


def _social_queue(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    rows = list_queue(settings, platform=args.platform or "", status=args.status or "")
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def _social_approve(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    count = approve_posts(settings, args.id or [], approve_all=args.all)
    print("承認しました: %d件" % count)


def _social_reject(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    if not reject_post(settings, args.id, args.reason):
        raise SystemExit("投稿IDが見つかりません")
    print("却下しました: %d" % args.id)


def _social_retry(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    if not retry_post(settings, args.id):
        raise SystemExit("承認済みの失敗投稿が見つかりません")
    print("再試行キューへ戻しました: %d" % args.id)


def _social_mark_published(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    if not mark_post_published(settings, args.id, permalink=args.permalink or "", external_id=args.external_id or ""):
        raise SystemExit("投稿IDが見つかりません")
    print("公開済みにしました: %d" % args.id)


def _social_reschedule(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    if not reschedule_post(settings, args.id, args.scheduled_at):
        raise SystemExit("予約変更できる投稿が見つかりません")
    print("予約時刻を変更しました: %d" % args.id)


def _social_export(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    count = export_queue(settings, Path(args.file), platform=args.platform or "", only_approved=not args.include_pending)
    print("CSV出力: %d件 %s" % (count, args.file))


def _social_import(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    result = import_manual_social_posts(settings, Path(args.file), platform=args.platform, approve=args.approve)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _social_discord(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    webhook = args.webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
    if args.send:
        if not webhook:
            raise SystemExit("DISCORD_WEBHOOK_URLまたは--webhook-urlが必要です")
        result = send_discord_ready_messages(
            settings,
            webhook,
            platform=args.platform,
            limit=args.limit,
            account_url=args.account_url or "",
        )
    else:
        result = discord_ready_messages(settings, platform=args.platform, limit=args.limit, account_url=args.account_url or "")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _social_dispatch(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    result = dispatch(settings, platform=args.platform or "", live=args.live, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _social_metric(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    add_social_metric(
        settings, args.post_id, args.measured_at, args.impressions, args.likes,
        args.replies, args.reposts, args.saves, args.link_clicks, args.source,
    )
    print("SNS指標を保存しました")


def _social_funnel_metric(args) -> None:
    settings = load_settings()
    add_funnel_metric(
        settings, args.post_id, args.measured_at, args.impressions, args.link_clicks,
        args.landing_sessions, args.engaged_seconds, args.conversions, args.revenue, args.source,
    )
    print("SNS→記事→成約指標を保存しました")


def _social_learning_report() -> None:
    result = write_learning_report(load_settings())
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _social_ab_release(args) -> None:
    count = release_b_variants(load_settings(), minimum_impressions=args.minimum_impressions)
    print("B案を解放しました: %d件" % count)


def _social_set_media(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    if not set_media_urls(settings, args.id, args.url):
        raise SystemExit("Instagram投稿IDが見つかりません")
    print("Instagram画像URLを登録しました")


def _social_render(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    files = render_carousel(settings, args.id, Path(args.output) if args.output else None)
    print(json.dumps([str(path) for path in files], ensure_ascii=False, indent=2))


def _build_site(args) -> None:
    settings = load_settings()
    result = build_static_site(settings, Path(args.output) if args.output else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _publish_check(args) -> None:
    settings = load_settings()
    result = check_publish_ready(settings, Path(args.output))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ready"]:
        raise SystemExit(2)


def _offer_add(args) -> None:
    settings = load_settings()
    values = {
        "offer_id": args.offer_id,
        "network": args.network,
        "name": args.name,
        "category": args.category,
        "keywords": "|".join(args.keyword or []),
        "problem_tags": "|".join(args.problem_tag or []),
        "event_tags": "|".join(args.event_tag or []),
        "affiliate_url": args.affiliate_url,
        "landing_url": args.landing_url or args.affiliate_url,
        "reward_type": args.reward_type,
        "reward_value": str(args.reward_value),
        "allowed_media": "|".join(args.allowed_media or ["site"]),
        "status": args.status,
        "last_verified_at": args.verified_at,
    }
    upsert_offer_csv(values)
    initialize(settings.database_path)
    import_offers(settings)
    print(json.dumps({"saved": True, "offer_id": args.offer_id, "status": args.status}, ensure_ascii=False, indent=2))


def _rakuten_search(args) -> None:
    client = RakutenProductClient()
    products = client.search(args.keyword, limit=args.limit)
    rows = []
    for product in products:
        rows.append({
            "name": product.name,
            "min_price": product.min_price,
            "max_price": product.max_price,
            "review_count": product.review_count,
            "review_average": product.review_average,
            "has_affiliate_url": bool(product.affiliate_url),
            "product_url": product.product_url,
        })
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def _product_scout(args) -> None:
    settings = load_settings()
    candidates = scout_page_products(
        settings,
        page_slug=args.page_slug,
        limit_per_keyword=args.limit_per_keyword,
        queries_per_group=args.queries_per_group,
        delay_seconds=args.delay_seconds,
        live_items=not args.product_catalog,
    )
    output = Path(args.output)
    write_candidates_csv(candidates, output)
    activated = activate_candidates(settings, candidates) if args.activate else 0
    site_result = build_static_site(settings, Path(args.site_output)) if args.build_site else None
    result = {
        "page_slug": args.page_slug,
        "candidate_count": len(candidates),
        "best_count": len(best_by_offer(candidates)),
        "activated": activated,
        "output": str(output),
        "site": site_result,
        "best": [
            {
                "offer_id": candidate.offer_id,
                "product_group": candidate.product_group,
                "name": candidate.name,
                "score": candidate.score,
                "min_price": candidate.min_price,
                "review_count": candidate.review_count,
                "review_average": candidate.review_average,
                "has_affiliate_url": bool(candidate.affiliate_url),
                "reasons": candidate.reasons,
            }
            for candidate in best_by_offer(candidates)
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _product_operations(args) -> None:
    settings = load_settings()
    result = run_product_operations(
        settings,
        mode=args.mode,
        apply_changes=not args.dry_run,
        build_site=not args.no_build_site,
        delay_seconds=args.delay_seconds,
        max_slots=args.limit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _product_expand_cache(args) -> None:
    settings = load_settings()
    initialize(settings.database_path)
    result = expand_products_from_cache(settings, target_per_page=args.target, refresh=args.refresh)
    if args.build_site:
        result["site"] = build_static_site(settings, Path(args.site_output))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _affiliate_metrics_import(args) -> None:
    result = import_affiliate_metrics(load_settings(), Path(args.file), source=args.source)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _affiliate_report(args) -> None:
    result = write_affiliate_performance_report(load_settings())
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _trend_screen(args) -> None:
    settings = load_settings()
    result = screen_trend_opportunities(
        settings,
        countries=args.country or ["JP", "US", "KR", "GB"],
        max_items=args.max_items,
        approve=args.approve,
        enqueue=not args.no_enqueue,
        include_ranking_only=not args.no_ranking_only,
    )
    if args.build_site:
        result["site"] = build_static_site(settings, Path(args.site_output))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _trend_enqueue_latest(args) -> None:
    result = enqueue_latest_opportunities(
        load_settings(), approve=args.approve, max_items=args.max_items,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _wordpress_check() -> None:
    print(json.dumps(WordPressPublisher().check_connection(), ensure_ascii=False, indent=2))


def _wordpress_draft(args) -> None:
    result = WordPressPublisher().create_draft_from_file(
        Path(args.file), title=args.title, slug=args.slug, excerpt=args.excerpt,
    )
    print(json.dumps({
        "id": result.get("id"),
        "status": result.get("status"),
        "link": result.get("link"),
        "edit": result.get("_links", {}).get("self", [{}])[0].get("href", ""),
    }, ensure_ascii=False, indent=2))


def _wordpress_sync(args) -> None:
    result = WordPressPublisher().sync_generated_site(Path(args.site_dir), status=args.status)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trend-commerce", description="AIトレンドコマースBOT")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="DBと出力先を初期化")
    sub.add_parser("seed", help="情報源と商品候補を登録")
    sub.add_parser("collect", help="RSS/Atomを収集")
    sub.add_parser("demo", help="無料オフラインデモを一括実行")
    sub.add_parser("report", help="CEOレポートを生成")
    sub.add_parser("status", help="状態をJSON表示")

    signal = sub.add_parser("add-signal", help="話題URLを手動投入")
    signal.add_argument("--title", required=True)
    signal.add_argument("--url", required=True)
    signal.add_argument("--summary", required=True)
    signal.add_argument("--category", choices=["季節・暮らし", "美容", "フィットネス", "健康", "AI・ガジェット"])

    run = sub.add_parser("run", help="採点・商品照合・下書き生成")
    run.add_argument("--allow-paid", action="store_true", help="OPENAI_API_KEYがある場合のみ有料AIを許可")

    review = sub.add_parser("review", help="CEOまたは品質部のレビューを記録")
    review.add_argument("--content-id", type=int, required=True)
    review.add_argument("--decision", required=True)
    review.add_argument("--notes", default="")

    conversions = sub.add_parser("import-conversions", help="ASP売上CSVを重複なしで取り込む")
    conversions.add_argument("--file", required=True)

    metric = sub.add_parser("add-metric", help="記事指標を手動登録・更新")
    metric.add_argument("--content-id", type=int, required=True)
    metric.add_argument("--measured-at", required=True)
    metric.add_argument("--sessions", type=int, default=0)
    metric.add_argument("--outbound-clicks", type=int, default=0)
    metric.add_argument("--conversions", type=int, default=0)
    metric.add_argument("--revenue", type=float, default=0)
    metric.add_argument("--source", default="manual")

    queue = sub.add_parser("social-queue", help="SNS投稿キューを表示")
    queue.add_argument("--platform", choices=["x", "threads", "instagram"])
    queue.add_argument("--status")

    approve = sub.add_parser("social-approve", help="SNS投稿を承認")
    approve_group = approve.add_mutually_exclusive_group(required=True)
    approve_group.add_argument("--id", type=int, action="append")
    approve_group.add_argument("--all", action="store_true")

    reject = sub.add_parser("social-reject", help="SNS投稿を却下")
    reject.add_argument("--id", type=int, required=True)
    reject.add_argument("--reason", required=True)

    retry = sub.add_parser("social-retry", help="失敗した承認済み投稿を再試行キューへ戻す")
    retry.add_argument("--id", type=int, required=True)

    mark = sub.add_parser("social-mark-published", help="手動投稿済みのSNSキューを公開済みにする")
    mark.add_argument("--id", type=int, required=True)
    mark.add_argument("--permalink", default="")
    mark.add_argument("--external-id", default="")

    reschedule = sub.add_parser("social-reschedule", help="SNS投稿の予約時刻を変更")
    reschedule.add_argument("--id", type=int, required=True)
    reschedule.add_argument("--scheduled-at", required=True, help="ISO 8601形式")

    export = sub.add_parser("social-export", help="手動投稿用CSVを出力")
    export.add_argument("--file", default="output/social/post_queue.csv")
    export.add_argument("--platform", choices=["x", "threads", "instagram"])
    export.add_argument("--include-pending", action="store_true")

    social_import = sub.add_parser("social-import", help="手動テスト投稿CSVをSNS投稿キューへ取り込む")
    social_import.add_argument("--file", required=True)
    social_import.add_argument("--platform", choices=["x", "threads", "instagram"], default="x")
    social_import.add_argument("--approve", action="store_true", help="取り込み時に承認済みreadyにする")

    social_discord = sub.add_parser("social-discord", help="ready投稿候補をDiscordへ送る/プレビューする")
    social_discord.add_argument("--platform", choices=["x", "threads", "instagram"], default="x")
    social_discord.add_argument("--limit", type=int, default=1)
    social_discord.add_argument("--account-url", default="https://x.com/m0506k")
    social_discord.add_argument("--webhook-url", default="")
    social_discord.add_argument("--send", action="store_true", help="Discord Webhookへ実送信する。未指定ならプレビューのみ")

    social_dispatch = sub.add_parser("social-dispatch", help="期限到来投稿をdry-runまたは実投稿")
    social_dispatch.add_argument("--platform", choices=["x", "threads", "instagram"])
    social_dispatch.add_argument("--limit", type=int, default=3)
    social_dispatch.add_argument("--live", action="store_true", help="実投稿。認証とSITE_BASE_URLが必須")

    social_metric = sub.add_parser("social-metric", help="SNS投稿の実績を手動登録")
    social_metric.add_argument("--post-id", type=int, required=True)
    social_metric.add_argument("--measured-at", required=True)
    social_metric.add_argument("--impressions", type=int, default=0)
    social_metric.add_argument("--likes", type=int, default=0)
    social_metric.add_argument("--replies", type=int, default=0)
    social_metric.add_argument("--reposts", type=int, default=0)
    social_metric.add_argument("--saves", type=int, default=0)
    social_metric.add_argument("--link-clicks", type=int, default=0)
    social_metric.add_argument("--source", default="manual")

    funnel_metric = sub.add_parser("social-funnel-metric", help="A/B投稿のCTR・滞在時間・CVRを登録")
    funnel_metric.add_argument("--post-id", type=int, required=True)
    funnel_metric.add_argument("--measured-at", required=True)
    funnel_metric.add_argument("--impressions", type=int, default=0)
    funnel_metric.add_argument("--link-clicks", type=int, default=0)
    funnel_metric.add_argument("--landing-sessions", type=int, default=0)
    funnel_metric.add_argument("--engaged-seconds", type=float, default=0, help="記事滞在秒数の合計")
    funnel_metric.add_argument("--conversions", type=int, default=0)
    funnel_metric.add_argument("--revenue", type=float, default=0)
    funnel_metric.add_argument("--source", default="manual")
    sub.add_parser("social-learning-report", help="A/Bテストの勝ちフックをCSV出力")
    ab_release = sub.add_parser("social-ab-release", help="A案の表示数が基準に達した話題のB案を解放")
    ab_release.add_argument("--minimum-impressions", type=int, default=500)

    media = sub.add_parser("social-set-media", help="Instagram投稿へ公開画像URLを設定")
    media.add_argument("--id", type=int, required=True)
    media.add_argument("--url", action="append", required=True)

    render = sub.add_parser("social-render", help="InstagramカルーセルPNGを生成")
    render.add_argument("--id", type=int, required=True)
    render.add_argument("--output")

    build_site = sub.add_parser("build-site", help="導入用の静的比較サイトをHTML出力")
    build_site.add_argument("--output", default="output/site")

    publish_check = sub.add_parser("publish-check", help="公開前の必須設定と出力物を検査")
    publish_check.add_argument("--output", default="output/site")

    offer_add = sub.add_parser("offer-add", help="実アフィリエイト商品リンクをoffers.csvへ追加/更新")
    offer_add.add_argument("--offer-id", required=True)
    offer_add.add_argument("--network", required=True, help="rakuten / amazon / moshimo / a8 など")
    offer_add.add_argument("--name", required=True)
    offer_add.add_argument("--category", required=True, choices=["季節・暮らし", "美容", "フィットネス", "健康", "AI・ガジェット"])
    offer_add.add_argument("--keyword", action="append", default=[])
    offer_add.add_argument("--problem-tag", action="append", default=[])
    offer_add.add_argument("--event-tag", action="append", default=[])
    offer_add.add_argument("--affiliate-url", required=True)
    offer_add.add_argument("--landing-url", default="")
    offer_add.add_argument("--reward-type", default="percent")
    offer_add.add_argument("--reward-value", type=float, default=0)
    offer_add.add_argument("--allowed-media", action="append", default=["site"])
    offer_add.add_argument("--status", choices=["research", "pending", "active", "paused"], default="active")
    offer_add.add_argument("--verified-at", default="2026-06-25")

    rakuten_search = sub.add_parser("rakuten-search", help="楽天APIで商品候補を検索")
    rakuten_search.add_argument("--keyword", required=True)
    rakuten_search.add_argument("--limit", type=int, default=5)

    product_scout = sub.add_parser("product-scout", help="比較ページの商品候補を楽天APIで選定")
    product_scout.add_argument("--page-slug", required=True)
    product_scout.add_argument("--limit-per-keyword", type=int, default=5)
    product_scout.add_argument("--queries-per-group", type=int, default=2)
    product_scout.add_argument("--delay-seconds", type=float, default=1.5)
    product_scout.add_argument("--product-catalog", action="store_true", help="販売中商品検索ではなく商品カタログ検索を使う")
    product_scout.add_argument("--output", default="output/products/rakuten_candidates.csv")
    product_scout.add_argument("--activate", action="store_true", help="各商品枠の最高スコア商品をoffers.csvへ反映")
    product_scout.add_argument("--build-site", action="store_true", help="反映後に導入サイトを再生成")
    product_scout.add_argument("--site-output", default="output/site")

    product_ops = sub.add_parser("product-ops", help="商品運用部BOTが販売監視・再評価・入替を実行")
    product_ops.add_argument("--mode", choices=["daily", "rotation"], default="daily")
    product_ops.add_argument("--dry-run", action="store_true", help="判断とレポートのみ。商品は変更しない")
    product_ops.add_argument("--no-build-site", action="store_true", help="商品反映後のサイト再生成を省略")
    product_ops.add_argument("--delay-seconds", type=float, default=1.1)
    product_ops.add_argument("--limit", type=int, default=0, help="検証用。0は全商品")

    product_expand = sub.add_parser("product-expand-cache", help="検証済み楽天候補から各比較ページの商品数を補完")
    product_expand.add_argument("--target", type=int, default=8)
    product_expand.add_argument("--refresh", action="store_true", help="以前のキャッシュ追加枠を再審査して入れ替える")
    product_expand.add_argument("--build-site", action="store_true")
    product_expand.add_argument("--site-output", default="output/site")

    affiliate_metrics = sub.add_parser("import-affiliate-metrics", help="GA4等の商品別クリック指標CSVを取り込む")
    affiliate_metrics.add_argument("--file", required=True)
    affiliate_metrics.add_argument("--source", default="ga4_csv")
    sub.add_parser("affiliate-report", help="商品別CTR・CVR・売上・EPCレポートを生成")

    trend_screen = sub.add_parser("trend-screen", help="国別トレンドと楽天売れ筋を照合してSNS候補を生成")
    trend_screen.add_argument("--country", action="append", choices=["JP", "US", "KR"], help="対象国。複数指定可")
    trend_screen.add_argument("--max-items", type=int, default=6)
    trend_screen.add_argument("--approve", action="store_true", help="X・Instagram候補を承認済みで登録")
    trend_screen.add_argument("--no-enqueue", action="store_true", help="SNSキューへ登録しない")
    trend_screen.add_argument("--no-ranking-only", action="store_true", help="ニュース一致のない楽天売れ筋候補を除外")
    trend_screen.add_argument("--build-site", action="store_true")
    trend_screen.add_argument("--site-output", default="output/site")
    trend_cached = sub.add_parser("trend-enqueue-latest", help="直近48時間の検証済み話題からSNS候補を生成")
    trend_cached.add_argument("--max-items", type=int, default=6)
    trend_cached.add_argument("--approve", action="store_true")
    sub.add_parser("wordpress-check", help="WordPress REST APIの接続を確認")
    wordpress_draft = sub.add_parser("wordpress-draft", help="Markdown記事をWordPressへ下書き投稿")
    wordpress_draft.add_argument("--file", required=True)
    wordpress_draft.add_argument("--title", default="")
    wordpress_draft.add_argument("--slug", default="")
    wordpress_draft.add_argument("--excerpt", default="")
    wordpress_sync = sub.add_parser("wordpress-sync", help="生成済みサイトをWordPress固定ページへ同期")
    wordpress_sync.add_argument("--site-dir", default="output/site")
    wordpress_sync.add_argument("--status", choices=["draft", "publish"], default="publish")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    handlers = {
        "init": lambda: _init(),
        "seed": lambda: _seed(),
        "collect": lambda: _collect(),
        "add-signal": lambda: _add_signal(args),
        "run": lambda: _run(args),
        "demo": lambda: _demo(),
        "report": lambda: _report(),
        "status": lambda: _status(),
        "review": lambda: _review(args),
        "import-conversions": lambda: _import_conversions(args),
        "add-metric": lambda: _add_metric(args),
        "social-queue": lambda: _social_queue(args),
        "social-approve": lambda: _social_approve(args),
        "social-reject": lambda: _social_reject(args),
        "social-retry": lambda: _social_retry(args),
        "social-mark-published": lambda: _social_mark_published(args),
        "social-reschedule": lambda: _social_reschedule(args),
        "social-export": lambda: _social_export(args),
        "social-import": lambda: _social_import(args),
        "social-discord": lambda: _social_discord(args),
        "social-dispatch": lambda: _social_dispatch(args),
        "social-metric": lambda: _social_metric(args),
        "social-funnel-metric": lambda: _social_funnel_metric(args),
        "social-learning-report": lambda: _social_learning_report(),
        "social-ab-release": lambda: _social_ab_release(args),
        "social-set-media": lambda: _social_set_media(args),
        "social-render": lambda: _social_render(args),
        "build-site": lambda: _build_site(args),
        "publish-check": lambda: _publish_check(args),
        "offer-add": lambda: _offer_add(args),
        "rakuten-search": lambda: _rakuten_search(args),
        "product-scout": lambda: _product_scout(args),
        "product-ops": lambda: _product_operations(args),
        "product-expand-cache": lambda: _product_expand_cache(args),
        "import-affiliate-metrics": lambda: _affiliate_metrics_import(args),
        "affiliate-report": lambda: _affiliate_report(args),
        "trend-screen": lambda: _trend_screen(args),
        "trend-enqueue-latest": lambda: _trend_enqueue_latest(args),
        "wordpress-check": lambda: _wordpress_check(),
        "wordpress-draft": lambda: _wordpress_draft(args),
        "wordpress-sync": lambda: _wordpress_sync(args),
    }
    handlers[args.command]()
