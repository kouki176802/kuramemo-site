from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

from .database import connect, initialize, transaction
from .settings import Settings


X_IMPRESSION_FACTORS = [
    "冒頭1行で、誰のどんな悩みに関係する話かを見せる",
    "どこで話題か、なぜ今見られているかを本文内で回収する",
    "価格やおすすめだけでなく、買う前に見る軸を1つ入れる",
    "URLなし投稿でも固定ポストやプロフィールへ自然に移動する理由を作る",
    "同じ商品でも、理由・失敗回避・向く人・比較軸でフックを変える",
    "断定しすぎず、読者が自分の状況に当てはめて考えられる余白を残す",
]


def information_gap_hooks(market_label: str, topic: str, reason: str) -> List[Dict[str, str]]:
    """Create honest hook variants whose answer is present in the post body."""
    market = market_label.strip("【】") or "いま注目"
    subject = topic.strip().rstrip("。！？")
    subject = subject if len(subject) <= 57 else subject[:56].rstrip() + "…"
    if market.startswith("日本"):
        place = "日本で注目"
    elif "で" in market:
        place = market.split("で", 1)[0] + "で注目"
    else:
        place = market
    reason_text = reason.strip()
    return [
        {
            "variant": "A",
            "hook_type": "reason_question",
            "text": "【%s】%s、なぜ今見られてる？" % (market, subject),
            "promise": reason_text,
        },
        {
            "variant": "B",
            "hook_type": "audience_gap",
            "text": "%sの「%s」 日本で選ぶなら先に見るべきこと" % (place, subject),
            "promise": reason_text,
        },
    ]


def x_post_quality_checks(text: str) -> Dict[str, bool]:
    """Lightweight lint for X posts before approval.

    This is intentionally heuristic.  It catches the weak patterns that make
    posts feel like a generic affiliate feed: no hook, no source context, no
    decision axis, or no next action.
    """
    clean = text.strip()
    first_line = clean.splitlines()[0] if clean else ""
    source_terms = (
        "韓国", "アメリカ", "米国", "海外", "日本", "ニュース", "SNS", "Google",
        "Yahoo", "ランキング", "PR TIMES", "話題", "注目", "伸び",
    )
    decision_terms = ("見る", "確認", "比較", "条件", "価格", "レビュー", "向く", "注意", "選ぶ", "失敗")
    action_terms = ("固定ポスト", "プロフィール", "くらメモ", "サイト", "リンク", "比較表", "記事")
    return {
        "has_gap_hook": any(
            token in first_line
            for token in ("なぜ", "理由", "先に", "失敗", "？", "?", "だけ", "ではない", "より", "伸び")
        ),
        "has_source_context": any(token in clean for token in source_terms),
        "has_decision_axis": any(token in clean for token in decision_terms),
        "has_next_action": any(token in clean for token in action_terms),
        "not_too_generic": "おすすめです" not in clean and "人気です" not in clean,
    }


def x_post_quality_score(text: str) -> int:
    checks = x_post_quality_checks(text)
    return int(round(sum(1 for ok in checks.values() if ok) / len(checks) * 100))


def register_experiment(conn, experiment_key: str, post_id: int, variant: str, hook_type: str, promise: str) -> None:
    conn.execute(
        """
        INSERT INTO social_experiments(experiment_key, social_post_id, variant, hook_type, promise_text)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(social_post_id) DO UPDATE SET
            experiment_key=excluded.experiment_key, variant=excluded.variant,
            hook_type=excluded.hook_type, promise_text=excluded.promise_text
        """,
        (experiment_key, post_id, variant, hook_type, promise),
    )


def add_funnel_metric(
    settings: Settings,
    post_id: int,
    measured_at: str,
    impressions: int = 0,
    link_clicks: int = 0,
    landing_sessions: int = 0,
    engaged_seconds: float = 0,
    conversions: int = 0,
    revenue: float = 0,
    source: str = "manual",
) -> None:
    initialize(settings.database_path)
    with transaction(settings.database_path) as conn:
        exists = conn.execute("SELECT id FROM social_posts WHERE id=?", (post_id,)).fetchone()
        if exists is None:
            raise ValueError("SNS投稿IDが見つかりません")
        conn.execute(
            """
            INSERT INTO social_funnel_metrics(
                social_post_id, measured_at, impressions, link_clicks, landing_sessions,
                engaged_seconds, conversions, revenue, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(social_post_id, measured_at, source) DO UPDATE SET
                impressions=excluded.impressions, link_clicks=excluded.link_clicks,
                landing_sessions=excluded.landing_sessions, engaged_seconds=excluded.engaged_seconds,
                conversions=excluded.conversions, revenue=excluded.revenue
            """,
            (post_id, measured_at, impressions, link_clicks, landing_sessions,
             engaged_seconds, conversions, revenue, source),
        )


def learning_rows(settings: Settings) -> List[Dict[str, object]]:
    initialize(settings.database_path)
    with connect(settings.database_path) as conn:
        rows = conn.execute(
            """
            SELECT e.experiment_key, e.variant, e.hook_type, p.platform, p.post_text,
                   COALESCE(SUM(m.impressions), 0) impressions,
                   COALESCE(SUM(m.link_clicks), 0) link_clicks,
                   COALESCE(SUM(m.landing_sessions), 0) landing_sessions,
                   COALESCE(SUM(m.engaged_seconds), 0) engaged_seconds,
                   COALESCE(SUM(m.conversions), 0) conversions,
                   COALESCE(SUM(m.revenue), 0) revenue
            FROM social_experiments e
            JOIN social_posts p ON p.id=e.social_post_id
            LEFT JOIN social_funnel_metrics m ON m.social_post_id=p.id
            GROUP BY e.social_post_id
            ORDER BY e.experiment_key, p.platform, e.variant
            """
        ).fetchall()
    result: List[Dict[str, object]] = []
    for raw in rows:
        row = dict(raw)
        impressions = int(row["impressions"])
        clicks = int(row["link_clicks"])
        sessions = int(row["landing_sessions"])
        conversions = int(row["conversions"])
        row["ctr"] = round(clicks / impressions * 100, 2) if impressions else 0.0
        row["avg_engaged_seconds"] = round(float(row["engaged_seconds"]) / sessions, 1) if sessions else 0.0
        row["cvr"] = round(conversions / clicks * 100, 2) if clicks else 0.0
        row["score"] = round(
            float(row["ctr"]) * 0.45 + min(float(row["avg_engaged_seconds"]), 120) / 120 * 25
            + float(row["cvr"]) * 0.30,
            2,
        )
        result.append(row)
    for row in result:
        peers = [r for r in result if r["experiment_key"] == row["experiment_key"] and r["platform"] == row["platform"]]
        enough = all(int(peer["impressions"]) >= 500 for peer in peers) and len(peers) >= 2
        best = max(peers, key=lambda peer: float(peer["score"])) if peers else row
        row["decision"] = "勝ちパターン" if enough and best is row else ("継続テスト" if not enough else "停止候補")
    return result


def write_learning_report(settings: Settings) -> Dict[str, object]:
    rows = learning_rows(settings)
    target = settings.output_dir / "social" / "learning_report.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "experiment_key", "platform", "variant", "hook_type", "impressions", "link_clicks",
        "ctr", "landing_sessions", "avg_engaged_seconds", "conversions", "cvr", "revenue",
        "score", "decision", "post_text",
    ]
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    return {"rows": len(rows), "path": str(target)}


def release_b_variants(settings: Settings, minimum_impressions: int = 500) -> int:
    """Release B only after its A variant has enough exposure to avoid duplicate-looking bursts."""
    initialize(settings.database_path)
    with transaction(settings.database_path) as conn:
        rows = conn.execute(
            """
            SELECT b.social_post_id, p.platform
            FROM social_experiments b
            JOIN social_posts p ON p.id=b.social_post_id
            WHERE b.variant='B' AND p.status='experiment_hold'
              AND EXISTS (
                SELECT 1 FROM social_experiments a
                JOIN social_posts pa ON pa.id=a.social_post_id
                JOIN social_funnel_metrics m ON m.social_post_id=a.social_post_id
                WHERE a.experiment_key=b.experiment_key AND a.variant='A'
                  AND pa.platform=p.platform
                GROUP BY a.social_post_id
                HAVING SUM(m.impressions) >= ?
              )
            """,
            (minimum_impressions,),
        ).fetchall()
        for row in rows:
            status = "media_required" if row["platform"] == "instagram" else "queued"
            conn.execute(
                "UPDATE social_posts SET status=?, scheduled_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, row["social_post_id"]),
            )
        return len(rows)
