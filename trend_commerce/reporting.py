from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Dict

from .database import connect
from .settings import Settings, ensure_directories


def report_data(settings: Settings) -> Dict[str, object]:
    with connect(settings.database_path) as conn:
        counts = {
            "signals": conn.execute("SELECT COUNT(*) AS c FROM raw_signals").fetchone()["c"],
            "events": conn.execute("SELECT COUNT(*) AS c FROM trend_events").fetchone()["c"],
            "offers": conn.execute("SELECT COUNT(*) AS c FROM offers").fetchone()["c"],
            "drafts": conn.execute("SELECT COUNT(*) AS c FROM content_items").fetchone()["c"],
            "blocked": conn.execute("SELECT COUNT(*) AS c FROM compliance_reports WHERE decision='blocked'").fetchone()["c"],
            "conversions": conn.execute("SELECT COUNT(*) AS c FROM conversions").fetchone()["c"],
            "revenue": conn.execute("SELECT COALESCE(SUM(amount), 0) AS c FROM conversions WHERE status IN ('approved', 'confirmed')").fetchone()["c"],
            "social_queued": conn.execute("SELECT COUNT(*) AS c FROM social_posts WHERE status='queued'").fetchone()["c"],
            "social_ready": conn.execute("SELECT COUNT(*) AS c FROM social_posts WHERE status='ready'").fetchone()["c"],
            "social_media_required": conn.execute("SELECT COUNT(*) AS c FROM social_posts WHERE status='media_required'").fetchone()["c"],
            "social_published": conn.execute("SELECT COUNT(*) AS c FROM social_posts WHERE status='published'").fetchone()["c"],
            "social_clicks": conn.execute("SELECT COALESCE(SUM(link_clicks), 0) AS c FROM social_metrics").fetchone()["c"],
        }
        top_events = conn.execute(
            "SELECT id, title, category, score_total, status FROM trend_events ORDER BY score_total DESC LIMIT 10"
        ).fetchall()
        pending = conn.execute(
            """
            SELECT ci.id, ci.title, ci.status, cr.factual_score, cr.trust_score, cr.dark_pattern_score
            FROM content_items ci LEFT JOIN compliance_reports cr ON cr.content_id=ci.id
            WHERE ci.status IN ('approval_required', 'revision_required', 'blocked')
            ORDER BY ci.created_at DESC LIMIT 20
            """
        ).fetchall()
        social_queue = conn.execute(
            """
            SELECT id, platform, scheduled_at, status, approval_status, substr(post_text, 1, 100) AS preview
            FROM social_posts WHERE status IN ('queued', 'ready', 'media_required', 'failed')
            ORDER BY scheduled_at, id LIMIT 30
            """
        ).fetchall()
    return {
        "counts": counts,
        "top_events": [dict(row) for row in top_events],
        "pending": [dict(row) for row in pending],
        "social_queue": [dict(row) for row in social_queue],
    }


def write_ceo_report(settings: Settings) -> Path:
    ensure_directories(settings)
    data = report_data(settings)
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    rows = "".join(
        "<tr><td>{id}</td><td>{title}</td><td>{category}</td><td>{score_total}</td><td>{status}</td></tr>".format(
            **{key: html.escape(str(value)) for key, value in event.items()}
        )
        for event in data["top_events"]
    )
    pending_rows = "".join(
        "<tr><td>{id}</td><td>{title}</td><td>{status}</td><td>{factual_score}</td><td>{trust_score}</td><td>{dark_pattern_score}</td></tr>".format(
            **{key: html.escape(str(value)) for key, value in item.items()}
        )
        for item in data["pending"]
    )
    social_rows = "".join(
        "<tr><td>{id}</td><td>{platform}</td><td>{scheduled_at}</td><td>{status}</td><td>{approval_status}</td><td>{preview}</td></tr>".format(
            **{key: html.escape(str(value)) for key, value in item.items()}
        )
        for item in data["social_queue"]
    )
    counts = data["counts"]
    document = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>CEOレポート</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:1100px;margin:40px auto;padding:0 20px;color:#202124}}.cards{{display:flex;gap:12px;flex-wrap:wrap}}.card{{padding:18px 24px;background:#f4f7fb;border-radius:12px}}table{{border-collapse:collapse;width:100%;margin:16px 0 32px}}th,td{{padding:10px;border-bottom:1px solid #ddd;text-align:left}}th{{background:#f8f8f8}}.notice{{padding:14px;background:#fff5d6;border-radius:8px}}</style></head>
<body><h1>CEO週次レポート</h1><p>作成: {timestamp}</p>
<div class="notice">現在はShadow Modeです。自動公開は無効で、すべて人間承認待ちです。</div>
<h2>会社の状態</h2><div class="cards">
<div class="card">シグナル<br><strong>{signals}</strong></div><div class="card">イベント<br><strong>{events}</strong></div>
<div class="card">商品候補<br><strong>{offers}</strong></div><div class="card">下書き<br><strong>{drafts}</strong></div>
<div class="card">SNS承認待ち<br><strong>{social_queued}</strong></div><div class="card">SNS投稿準備済み<br><strong>{social_ready}</strong></div>
<div class="card">画像待ち<br><strong>{social_media_required}</strong></div>
<div class="card">SNS投稿済み<br><strong>{social_published}</strong></div><div class="card">SNSクリック<br><strong>{social_clicks}</strong></div>
<div class="card">ブロック<br><strong>{blocked}</strong></div><div class="card">承認売上<br><strong>¥{revenue:,.0f}</strong></div></div>
<h2>商機ランキング</h2><table><thead><tr><th>ID</th><th>話題</th><th>カテゴリ</th><th>点数</th><th>状態</th></tr></thead><tbody>{rows}</tbody></table>
<h2>CEO・品質確認待ち</h2><table><thead><tr><th>ID</th><th>記事</th><th>状態</th><th>事実</th><th>信頼</th><th>ダーク</th></tr></thead><tbody>{pending_rows}</tbody></table>
<h2>SNS投稿キュー</h2><table><thead><tr><th>ID</th><th>媒体</th><th>予定</th><th>状態</th><th>承認</th><th>内容</th></tr></thead><tbody>{social_rows}</tbody></table>
</body></html>""".format(
        timestamp=timestamp, rows=rows, pending_rows=pending_rows, social_rows=social_rows, **counts
    )
    path = settings.output_dir / "reports" / "ceo_report.html"
    path.write_text(document, encoding="utf-8")
    return path
