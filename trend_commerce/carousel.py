from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .database import connect, transaction
from .settings import Settings


def _font_path() -> str:
    candidates = (
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return ""


def _wrap(draw, text: str, font, max_width: int) -> List[str]:
    lines: List[str] = []
    current = ""
    for character in text:
        proposed = current + character
        width = draw.textbbox((0, 0), proposed, font=font)[2]
        if current and width > max_width:
            lines.append(current)
            current = character
        else:
            current = proposed
    if current:
        lines.append(current)
    return lines


def render_carousel(settings: Settings, post_id: int, output: Path | None = None) -> List[Path]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("カルーセル生成にはPillowが必要です。Codex付属Pythonで実行してください") from exc

    with connect(settings.database_path) as conn:
        row = conn.execute(
            "SELECT id, media_json FROM social_posts WHERE id=? AND platform='instagram'",
            (post_id,),
        ).fetchone()
    if row is None:
        raise ValueError("Instagram投稿IDが見つかりません")
    media = json.loads(row["media_json"] or "{}")
    slides = media.get("slides", [])
    if not slides:
        raise ValueError("スライド文がありません")

    target = output or settings.output_dir / "social" / ("instagram-%d" % post_id)
    target.mkdir(parents=True, exist_ok=True)
    font_path = _font_path()
    title_font = ImageFont.truetype(font_path, 62) if font_path else ImageFont.load_default()
    small_font = ImageFont.truetype(font_path, 34) if font_path else ImageFont.load_default()
    files: List[Path] = []
    for index, slide in enumerate(slides, start=1):
        image = Image.new("RGB", (1080, 1350), "#F7F2E8")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((70, 70, 1010, 1280), radius=45, fill="#FFFFFF")
        draw.rounded_rectangle((110, 115, 310, 180), radius=30, fill="#184D47")
        draw.text((145, 128), "TREND", font=small_font, fill="#FFFFFF")
        draw.text((850, 125), "%d/%d" % (index, len(slides)), font=small_font, fill="#184D47")
        slide_text = str(slide)
        prefix = "%d枚目:" % index
        if slide_text.startswith(prefix):
            slide_text = slide_text[len(prefix):].strip()
        active_font = title_font
        lines = _wrap(draw, slide_text, active_font, 780)
        line_height = 92
        total_height = len(lines) * line_height
        y = max(300, (1350 - total_height) // 2)
        for line in lines:
            draw.text((150, y), line, font=active_font, fill="#172121")
            y += line_height
        draw.line((150, 1120, 930, 1120), fill="#D9A441", width=8)
        draw.text((150, 1160), "広告を含みます｜詳しくは記事へ", font=small_font, fill="#4D5555")
        path = target / ("slide-%02d.png" % index)
        image.save(path, "PNG", optimize=True)
        files.append(path)

    media["local_paths"] = [str(path) for path in files]
    with transaction(settings.database_path) as conn:
        conn.execute(
            "UPDATE social_posts SET media_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (json.dumps(media, ensure_ascii=False), post_id),
        )
    return files
