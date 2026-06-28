from __future__ import annotations

import csv
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .database import connect, transaction
from .settings import Settings
from .utils import normalize_text, now_iso, stable_hash


PLATFORM_LIMITS = {"x": 280, "threads": 500, "instagram": 2200}
PLATFORM_INTERVALS = {"x": 30, "threads": 45, "instagram": 180}
URL_WEIGHT = 23
URL_PATTERN = re.compile(r"https?://\S+")


@dataclass
class PublishResult:
    external_id: str
    permalink: str
    raw: Dict[str, object]


def _article_url(settings: Settings, slug: str) -> str:
    if settings.site_base_url:
        return "%s/%s/" % (settings.site_base_url, slug)
    return "{ARTICLE_URL:%s}" % slug


def _disclosure(platform: str) -> str:
    return "※広告を含む記事です" if platform in {"x", "threads"} else "広告を含みます。"


def _x_weighted_len(text: str) -> int:
    """Approximate X weighted text length.

    X wraps URLs with t.co and CJK/full-width characters are safer to
    treat as double-width. This deliberately errs on the conservative side
    for Japanese BOT posts.
    """
    total = 0
    last = 0
    for match in URL_PATTERN.finditer(text):
        total += _x_weighted_len_no_urls(text[last:match.start()])
        total += URL_WEIGHT
        last = match.end()
    total += _x_weighted_len_no_urls(text[last:])
    return total


def _x_weighted_len_no_urls(text: str) -> int:
    total = 0
    for char in text:
        total += 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
    return total


def _platform_len(text: str, platform: str) -> int:
    return _x_weighted_len(text) if platform == "x" else len(text)


def _trim_to_platform_limit(text: str, platform: str) -> str:
    clean = " ".join(text.split())
    limit = PLATFORM_LIMITS[platform]
    if _platform_len(clean, platform) <= limit:
        return clean
    allowed = []
    for char in clean:
        candidate = "".join(allowed + [char]).rstrip() + "…"
        if _platform_len(candidate, platform) > limit:
            break
        allowed.append(char)
    return "".join(allowed).rstrip() + "…"


def _fit_text(text: str, platform: str, target_url: str) -> str:
    disclosure = _disclosure(platform)
    suffix = "\n\n%s" % disclosure
    if platform in {"x", "threads"}:
        suffix += "\n%s" % target_url
    limit = PLATFORM_LIMITS[platform]
    if platform == "instagram":
        clean = re.sub(r"[^\S\n]+", " ", text)
        clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    else:
        clean = " ".join(text.split())
    if _platform_len(clean + suffix, platform) > limit:
        allowed = []
        for char in clean:
            candidate = "".join(allowed + [char]).rstrip() + "…" + suffix
            if _platform_len(candidate, platform) > limit:
                break
            allowed.append(char)
        clean = "".join(allowed).rstrip() + "…"
    return clean + suffix


def _ensure_manual_content(conn) -> int:
    event = conn.execute("SELECT id FROM trend_events WHERE canonical_topic='manual-social-test'").fetchone()
    if event is None:
        cursor = conn.execute(
            """
            INSERT INTO trend_events(canonical_topic, title, summary, category, status)
            VALUES ('manual-social-test', '手動SNS投稿テスト', 'CSVから取り込んだ手動/半自動投稿候補', 'AI・ガジェット', 'detected')
            """
        )
        event_id = int(cursor.lastrowid)
    else:
        event_id = int(event["id"])
    content = conn.execute("SELECT id FROM content_items WHERE slug='manual-social-test'").fetchone()
    if content is None:
        cursor = conn.execute(
            """
            INSERT INTO content_items(event_id, content_type, title, slug, file_path, status, generator)
            VALUES (?, 'social_manual', '手動SNS投稿テスト', 'manual-social-test', 'samples/social/x_bot_test_posts.csv', 'draft', 'manual_csv')
            """,
            (event_id,),
        )
        return int(cursor.lastrowid)
    return int(content["id"])


def _next_schedule(conn, platform: str, base: Optional[datetime] = None) -> str:
    current = base or datetime.now(timezone.utc)
    row = conn.execute(
        "SELECT MAX(scheduled_at) AS latest FROM social_posts WHERE platform=? AND status IN ('queued', 'ready')",
        (platform,),
    ).fetchone()
    if row and row["latest"]:
        try:
            latest = datetime.fromisoformat(row["latest"])
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
            current = max(current, latest + timedelta(minutes=PLATFORM_INTERVALS[platform]))
        except ValueError:
            pass
    return current.replace(microsecond=0).isoformat()


def enqueue_social_assets(
    conn,
    settings: Settings,
    content_id: int,
    slug: str,
    assets: Dict[str, List[str]],
) -> int:
    target_url = _article_url(settings, slug)
    inserted = 0
    for platform in ("x", "threads"):
        for index, text in enumerate(assets.get(platform, []), start=1):
            variant = "%s-%d" % (platform, index)
            fitted = _fit_text(text, platform, target_url)
            fingerprint = stable_hash(platform, normalize_text(fitted), target_url)
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO social_posts(
                    content_id, platform, variant_key, post_text, target_url, media_json,
                    fingerprint, scheduled_at, status, approval_status
                ) VALUES (?, ?, ?, ?, ?, '{}', ?, ?, 'queued', 'pending')
                """,
                (content_id, platform, variant, fitted, target_url, fingerprint, _next_schedule(conn, platform)),
            )
            inserted += int(cursor.rowcount > 0)

    slides = assets.get("instagram", [])
    if slides:
        platform = "instagram"
        caption = _fit_text("話題の商品を、買う・待つ・不要の3つに整理しました。詳細はプロフィールのリンクから確認できます。", platform, target_url)
        media = json.dumps({"slides": slides, "media_urls": []}, ensure_ascii=False)
        fingerprint = stable_hash(platform, normalize_text(caption), "|".join(slides), target_url)
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO social_posts(
                content_id, platform, variant_key, post_text, target_url, media_json,
                fingerprint, scheduled_at, status, approval_status
            ) VALUES (?, 'instagram', 'instagram-carousel-1', ?, ?, ?, ?, ?, 'media_required', 'pending')
            """,
            (content_id, caption, target_url, media, fingerprint, _next_schedule(conn, platform)),
        )
        inserted += int(cursor.rowcount > 0)
    return inserted


def import_manual_social_posts(
    settings: Settings,
    path: Path,
    platform: str = "x",
    approve: bool = False,
) -> Dict[str, int]:
    inserted = 0
    skipped = 0
    updated = 0
    if platform not in PLATFORM_LIMITS:
        raise ValueError("未対応プラットフォーム: %s" % platform)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    with transaction(settings.database_path) as conn:
        content_id = _ensure_manual_content(conn)
        for row in rows:
            status = (row.get("status") or "").strip()
            if status in {"posted", "published", "rejected"} or (row.get("posted_url") or "").strip():
                skipped += 1
                continue
            post_text = (row.get("post_text") or row.get("text") or "").strip()
            if not post_text:
                skipped += 1
                continue
            row_platform = (row.get("platform") or platform).strip() or platform
            if row_platform not in PLATFORM_LIMITS:
                skipped += 1
                continue
            fitted = _trim_to_platform_limit(post_text, row_platform)
            variant_source = row.get("post_no") or row.get("stage") or stable_hash(fitted)[:8]
            variant = "manual-%s-%s" % (row_platform, variant_source)
            target_url = (row.get("target_url") or "").strip()
            fingerprint = stable_hash("manual", row_platform, normalize_text(fitted), target_url)
            approval_status = "approved" if approve else "pending"
            queue_status = "ready" if approve else "queued"
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO social_posts(
                    content_id, platform, variant_key, post_text, target_url, media_json,
                    fingerprint, scheduled_at, status, approval_status
                ) VALUES (?, ?, ?, ?, ?, '{}', ?, ?, ?, ?)
                """,
                (
                    content_id, row_platform, variant, fitted, target_url, fingerprint,
                    _next_schedule(conn, row_platform), queue_status, approval_status,
                ),
            )
            if cursor.rowcount:
                inserted += 1
            else:
                updated += 1
    return {"inserted": inserted, "skipped": skipped, "duplicates": updated}


def list_queue(settings: Settings, platform: str = "", status: str = "") -> List[Dict[str, object]]:
    sql = "SELECT * FROM social_posts WHERE 1=1"
    params: List[object] = []
    if platform:
        sql += " AND platform=?"
        params.append(platform)
    if status:
        sql += " AND status=?"
        params.append(status)
    sql += " ORDER BY scheduled_at, id"
    with connect(settings.database_path) as conn:
        return [dict(row) for row in conn.execute(sql, params)]


def approve_posts(settings: Settings, ids: Sequence[int], approve_all: bool = False) -> int:
    with transaction(settings.database_path) as conn:
        if approve_all:
            cursor = conn.execute(
                "UPDATE social_posts SET approval_status='approved', status='ready', updated_at=CURRENT_TIMESTAMP WHERE status='queued' AND approval_status='pending'"
            )
            return cursor.rowcount
        count = 0
        for post_id in ids:
            cursor = conn.execute(
                "UPDATE social_posts SET approval_status='approved', status='ready', updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='queued'",
                (post_id,),
            )
            count += cursor.rowcount
        return count


def reject_post(settings: Settings, post_id: int, reason: str) -> bool:
    with transaction(settings.database_path) as conn:
        cursor = conn.execute(
            "UPDATE social_posts SET approval_status='rejected', status='rejected', last_error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (reason, post_id),
        )
        return cursor.rowcount > 0


def retry_post(settings: Settings, post_id: int) -> bool:
    """Return a failed, already-approved post to the ready queue."""
    with transaction(settings.database_path) as conn:
        cursor = conn.execute(
            """
            UPDATE social_posts SET status='ready', last_error='', updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND status='failed' AND approval_status='approved'
            """,
            (post_id,),
        )
        return cursor.rowcount > 0


def mark_post_published(settings: Settings, post_id: int, permalink: str = "", external_id: str = "") -> bool:
    with transaction(settings.database_path) as conn:
        cursor = conn.execute(
            """
            UPDATE social_posts SET status='published', approval_status='approved', permalink=?, external_id=?,
                published_at=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (permalink, external_id, now_iso(), post_id),
        )
        if cursor.rowcount:
            conn.execute(
                "INSERT INTO social_post_attempts(social_post_id, mode, status, response_json) VALUES (?, 'manual', 'success', ?)",
                (post_id, json.dumps({"permalink": permalink, "external_id": external_id}, ensure_ascii=False)),
            )
        return cursor.rowcount > 0


def reschedule_post(settings: Settings, post_id: int, scheduled_at: str) -> bool:
    try:
        parsed = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("scheduled-atはISO 8601形式で指定してください") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    normalized = parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    with transaction(settings.database_path) as conn:
        cursor = conn.execute(
            """
            UPDATE social_posts SET scheduled_at=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND status IN ('queued', 'ready', 'failed', 'media_required')
            """,
            (normalized, post_id),
        )
        return cursor.rowcount > 0


def set_media_urls(settings: Settings, post_id: int, urls: Sequence[str]) -> bool:
    if not urls or any(not url.startswith("https://") for url in urls):
        raise ValueError("公開HTTPS画像URLを1件以上指定してください")
    with transaction(settings.database_path) as conn:
        row = conn.execute("SELECT media_json FROM social_posts WHERE id=? AND platform='instagram'", (post_id,)).fetchone()
        if row is None:
            return False
        media = json.loads(row["media_json"] or "{}")
        media["media_urls"] = list(urls)
        conn.execute(
            "UPDATE social_posts SET media_json=?, status='queued', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (json.dumps(media, ensure_ascii=False), post_id),
        )
        return True


def export_queue(settings: Settings, path: Path, platform: str = "", only_approved: bool = True) -> int:
    posts = list_queue(settings, platform=platform)
    if only_approved:
        posts = [post for post in posts if post["approval_status"] == "approved" and post["status"] == "ready"]
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["id", "platform", "scheduled_at", "post_text", "target_url", "media_json", "approval_status", "status"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(posts)
    return len(posts)


def _discord_message_for_post(post: Dict[str, object], account_url: str = "") -> str:
    platform = str(post["platform"])
    compose_url = "https://x.com/compose/post" if platform == "x" else ""
    post_text = str(post["post_text"])
    intent_url = ""
    if platform == "x":
        intent_url = "https://twitter.com/intent/tweet?text=%s" % urllib.parse.quote(post_text, safe="")
    lines = [
        "📝 **SNS投稿候補 #%s / %s**" % (post["id"], platform),
        "",
    ]
    if account_url:
        lines.append("アカウント: %s" % account_url)
    if compose_url:
        lines.append("投稿画面: %s" % compose_url)
    if intent_url:
        lines.append("本文入り投稿URL: %s" % intent_url)
    if post.get("target_url"):
        lines.append("誘導URL: %s" % post["target_url"])
    if platform == "instagram":
        try:
            media = json.loads(str(post.get("media_json") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            media = {}
        slides = media.get("slides", []) if isinstance(media, dict) else []
        if slides:
            lines.extend(["", "**カルーセル構成**"])
            for index, slide in enumerate(slides[:7], 1):
                lines.append("%s. %s" % (index, str(slide).replace("\n", " / ")[:120]))
    lines.extend([
        "",
        "**コピペ用投稿文**",
        "```",
        post_text.replace("```", "'''"),
        "```",
        "",
        "**投稿後に記録**",
        "```bash",
        "python3 -m trend_commerce social-mark-published --id %s --permalink 投稿URL" % post["id"],
        "```",
    ])
    message = "\n".join(lines)
    return message[:1990]


def discord_ready_messages(settings: Settings, platform: str = "x", limit: int = 1, account_url: str = "") -> List[Dict[str, object]]:
    # Discord is a delivery channel, not the final publish state.  Keep the
    # social post itself ready for the CEO to publish, but do not notify the
    # same row every time the scheduled job runs.
    with connect(settings.database_path) as conn:
        posts = [
            dict(row)
            for row in conn.execute(
                """
                SELECT p.*
                FROM social_posts p
                WHERE p.platform=?
                  AND (
                    p.status='ready'
                    OR (p.platform='instagram' AND p.status='media_required')
                  )
                  AND p.approval_status='approved'
                  AND NOT EXISTS (
                    SELECT 1 FROM social_post_attempts a
                    WHERE a.social_post_id=p.id
                      AND a.mode='discord'
                      AND a.status='success'
                  )
                ORDER BY p.scheduled_at, p.id
                LIMIT ?
                """,
                (platform, max(1, limit)),
            )
        ]
    result = []
    for post in posts:
        result.append({
            "id": post["id"],
            "platform": post["platform"],
            "content": _discord_message_for_post(post, account_url),
            "media_json": post.get("media_json", "{}"),
        })
    return result


def _discord_multipart(payload: Dict[str, object], paths: List[Path]) -> tuple[bytes, str]:
    boundary = "----kuramemo%s" % uuid.uuid4().hex
    chunks: List[bytes] = []
    chunks.extend([
        ("--%s\r\n" % boundary).encode(),
        b'Content-Disposition: form-data; name="payload_json"\r\n',
        b"Content-Type: application/json; charset=utf-8\r\n\r\n",
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        b"\r\n",
    ])
    for index, path in enumerate(paths[:10]):
        chunks.extend([
            ("--%s\r\n" % boundary).encode(),
            ('Content-Disposition: form-data; name="files[%d]"; filename="%s"\r\n' % (index, path.name)).encode(),
            b"Content-Type: image/png\r\n\r\n",
            path.read_bytes(),
            b"\r\n",
        ])
    chunks.append(("--%s--\r\n" % boundary).encode())
    return b"".join(chunks), "multipart/form-data; boundary=%s" % boundary


def send_discord_ready_messages(
    settings: Settings,
    webhook_url: str,
    platform: str = "x",
    limit: int = 1,
    account_url: str = "",
) -> List[Dict[str, object]]:
    if not webhook_url.startswith("https://discord.com/api/webhooks/") and not webhook_url.startswith("https://discordapp.com/api/webhooks/"):
        raise ValueError("Discord Webhook URLが不正です")
    results = []
    for message in discord_ready_messages(settings, platform=platform, limit=limit, account_url=account_url):
        payload = {
            "content": str(message["content"]),
            "username": "くらべメモBOT",
            "allowed_mentions": {"parse": []},
        }
        local_paths: List[Path] = []
        if message["platform"] == "instagram":
            try:
                media = json.loads(str(message.get("media_json") or "{}"))
                local_paths = [Path(value) for value in media.get("local_paths", []) if Path(value).exists()]
            except (TypeError, ValueError, json.JSONDecodeError):
                local_paths = []
            if not local_paths:
                try:
                    from .carousel import render_carousel
                    local_paths = render_carousel(settings, int(message["id"]))
                except RuntimeError:
                    local_paths = []
        if local_paths:
            request_data, content_type = _discord_multipart(payload, local_paths)
        else:
            request_data = json.dumps(payload).encode("utf-8")
            content_type = "application/json"
        request = urllib.request.Request(
            webhook_url,
            data=request_data,
            headers={
                "Content-Type": content_type,
                "User-Agent": "trend-commerce-discord-bridge/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
        with transaction(settings.database_path) as conn:
            conn.execute(
                """
                INSERT INTO social_post_attempts(social_post_id, mode, status, response_json)
                VALUES (?, 'discord', 'success', ?)
                """,
                (
                    message["id"],
                    json.dumps({"delivered": True, "platform": message["platform"]}, ensure_ascii=False),
                ),
            )
        results.append({"id": message["id"], "platform": message["platform"], "sent": True})
    return results


class XPublisher:
    def __init__(self) -> None:
        self.token = os.environ["X_USER_ACCESS_TOKEN"]

    def publish(self, post: Dict[str, object]) -> PublishResult:
        payload = {"text": post["post_text"], "paid_partnership": True}
        request = urllib.request.Request(
            "https://api.x.com/2/tweets",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Bearer %s" % self.token, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = json.loads(response.read().decode("utf-8"))
        post_id = str(raw.get("data", {}).get("id", ""))
        return PublishResult(post_id, "https://x.com/i/web/status/%s" % post_id if post_id else "", raw)


class ThreadsPublisher:
    def __init__(self) -> None:
        self.user_id = os.environ["THREADS_USER_ID"]
        self.token = os.environ["THREADS_ACCESS_TOKEN"]
        self.base = "https://graph.threads.net/v1.0"

    def _post_form(self, endpoint: str, params: Dict[str, str]) -> Dict[str, object]:
        data = urllib.parse.urlencode(params).encode("utf-8")
        request = urllib.request.Request(endpoint, data=data, method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def publish(self, post: Dict[str, object]) -> PublishResult:
        container = self._post_form(
            "%s/%s/threads" % (self.base, self.user_id),
            {"media_type": "TEXT", "text": str(post["post_text"]), "access_token": self.token},
        )
        creation_id = str(container.get("id", ""))
        published = self._post_form(
            "%s/%s/threads_publish" % (self.base, self.user_id),
            {"creation_id": creation_id, "access_token": self.token},
        )
        post_id = str(published.get("id", ""))
        return PublishResult(post_id, "", {"container": container, "published": published})


class InstagramPublisher:
    def __init__(self) -> None:
        self.user_id = os.environ["INSTAGRAM_USER_ID"]
        self.token = os.environ["INSTAGRAM_ACCESS_TOKEN"]
        version = os.getenv("META_GRAPH_VERSION", "v24.0")
        self.base = "https://graph.instagram.com/%s" % version

    def _post_form(self, endpoint: str, params: Dict[str, str]) -> Dict[str, object]:
        request = urllib.request.Request(endpoint, data=urllib.parse.urlencode(params).encode("utf-8"), method="POST")
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    def publish(self, post: Dict[str, object]) -> PublishResult:
        media = json.loads(str(post["media_json"]))
        urls = media.get("media_urls", [])
        if not urls:
            raise ValueError("Instagram自動投稿には公開HTTPS画像URLが必要です")
        child_ids = []
        for url in urls:
            child = self._post_form(
                "%s/%s/media" % (self.base, self.user_id),
                {"image_url": url, "is_carousel_item": "true", "access_token": self.token},
            )
            child_ids.append(str(child["id"]))
        container = self._post_form(
            "%s/%s/media" % (self.base, self.user_id),
            {
                "media_type": "CAROUSEL", "children": ",".join(child_ids),
                "caption": str(post["post_text"]), "access_token": self.token,
            },
        )
        published = self._post_form(
            "%s/%s/media_publish" % (self.base, self.user_id),
            {"creation_id": str(container["id"]), "access_token": self.token},
        )
        post_id = str(published.get("id", ""))
        return PublishResult(post_id, "", {"container": container, "published": published})


def _publisher(platform: str):
    if platform == "x":
        return XPublisher()
    if platform == "threads":
        return ThreadsPublisher()
    if platform == "instagram":
        return InstagramPublisher()
    raise ValueError("未対応プラットフォーム: %s" % platform)


def due_posts(settings: Settings, platform: str = "", now: Optional[str] = None) -> List[Dict[str, object]]:
    current = now or now_iso()
    sql = "SELECT * FROM social_posts WHERE status='ready' AND approval_status='approved' AND scheduled_at<=?"
    params: List[object] = [current]
    if platform:
        sql += " AND platform=?"
        params.append(platform)
    sql += " ORDER BY scheduled_at, id"
    with connect(settings.database_path) as conn:
        return [dict(row) for row in conn.execute(sql, params)]


def dispatch(settings: Settings, platform: str = "", live: bool = False, limit: int = 3) -> List[Dict[str, object]]:
    posts = due_posts(settings, platform=platform)[:limit]
    results: List[Dict[str, object]] = []
    for post in posts:
        if not live:
            results.append({"id": post["id"], "platform": post["platform"], "mode": "dry-run", "text": post["post_text"]})
            continue
        if "{ARTICLE_URL:" in str(post["post_text"]) or "{ARTICLE_URL:" in str(post["target_url"]):
            raise ValueError("SITE_BASE_URL未設定のため実投稿を停止しました")
        publisher = _publisher(str(post["platform"]))
        try:
            result = publisher.publish(post)
            with transaction(settings.database_path) as conn:
                conn.execute(
                    """
                    UPDATE social_posts SET status='published', external_id=?, permalink=?, attempts=attempts+1,
                        last_error='', published_at=?, updated_at=CURRENT_TIMESTAMP WHERE id=?
                    """,
                    (result.external_id, result.permalink, now_iso(), post["id"]),
                )
                conn.execute(
                    "INSERT INTO social_post_attempts(social_post_id, mode, status, response_json) VALUES (?, 'live', 'success', ?)",
                    (post["id"], json.dumps(result.raw, ensure_ascii=False)),
                )
            results.append({"id": post["id"], "platform": post["platform"], "external_id": result.external_id})
        except Exception as exc:
            with transaction(settings.database_path) as conn:
                conn.execute(
                    "UPDATE social_posts SET status='failed', attempts=attempts+1, last_error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (str(exc), post["id"]),
                )
                conn.execute(
                    "INSERT INTO social_post_attempts(social_post_id, mode, status, error) VALUES (?, 'live', 'failed', ?)",
                    (post["id"], str(exc)),
                )
            results.append({"id": post["id"], "platform": post["platform"], "error": str(exc)})
    return results


def add_social_metric(
    settings: Settings,
    post_id: int,
    measured_at: str,
    impressions: int = 0,
    likes: int = 0,
    replies: int = 0,
    reposts: int = 0,
    saves: int = 0,
    link_clicks: int = 0,
    source: str = "manual",
) -> None:
    with transaction(settings.database_path) as conn:
        conn.execute(
            """
            INSERT INTO social_metrics(
                social_post_id, measured_at, impressions, likes, replies, reposts, saves, link_clicks, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(social_post_id, measured_at, source) DO UPDATE SET
                impressions=excluded.impressions, likes=excluded.likes, replies=excluded.replies,
                reposts=excluded.reposts, saves=excluded.saves, link_clicks=excluded.link_clicks
            """,
            (post_id, measured_at, impressions, likes, replies, reposts, saves, link_clicks, source),
        )
