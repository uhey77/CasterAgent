from __future__ import annotations

import re
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

from PIL import Image, ImageDraw, ImageFont

from ...core.settings import AppSettings
from ...application.ports import ThumbnailGenerator
from ...domain.models import Article, Script, VideoMetadata

JST = timezone(timedelta(hours=9))


class ThumbnailGeneratorService(ThumbnailGenerator):
    """シンプルなPILベースのサムネイル自動生成"""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._images_dir = self._settings.storage.images_dir

    def generate(self, article: Article, metadata: VideoMetadata, script: Script | None = None) -> Path:
        self._images_dir.mkdir(parents=True, exist_ok=True)
        date_label = self._format_date_label(article)
        topics = self._select_topics(article, max_items=3)
        output_path = (self._images_dir / f"{article.article_id}_thumbnail.png").resolve()
        self._render_thumbnail(date_label, topics, output_path)
        return output_path

    def _format_date_label(self, article: Article) -> str:
        if article.published_at:
            dt = article.published_at.astimezone(JST)
        else:
            dt = datetime.now(JST)
        return dt.strftime("%m.%d")

    def _select_topics(self, article: Article, max_items: int = 3) -> List[str]:
        topics: List[str] = []
        for line in article.markdown_body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("###"):
                title = re.sub(r"^#+\s*", "", stripped)
                title = re.sub(r"^\d+[\.\)]\s*", "", title).strip(":- ")
                if title:
                    topics.append(title)
            if len(topics) >= max_items:
                break

        if not topics and article.title:
            topics.append(article.title)

        filler = ["最新トピック", "AIニュース", "アップデート"]
        while len(topics) < max_items and filler:
            topics.append(filler.pop(0))

        return [self._shorten(topic, max_chars=40) for topic in topics[:max_items]]

    def _shorten(self, text: str, max_chars: int = 40) -> str:
        return textwrap.shorten(text, width=max_chars, placeholder="…")

    def _render_thumbnail(self, date_label: str, topics: List[str], output_path: Path) -> None:
        width, height = 1280, 720
        img = Image.new("RGB", (width, height), "#0c1021")
        draw = ImageDraw.Draw(img, "RGBA")

        self._draw_gradient_background(draw, width, height)

        title_font = self._load_font(64)
        subtitle_font = self._load_font(42)
        topic_font = self._load_font(48)
        small_font = self._load_font(28)

        header_box = (40, 40, width - 40, 180)
        draw.rounded_rectangle(header_box, radius=28, fill=(30, 50, 110, 220))
        draw.text((70, 62), f"AI Daily {date_label}", font=title_font, fill=(245, 247, 255))
        draw.text((70, 130), "本日のトップ3", font=subtitle_font, fill=(210, 220, 255))

        list_top = 220
        list_left = 70
        line_height = 130
        colors = [(79, 141, 255, 210), (104, 208, 173, 210), (255, 149, 128, 210)]

        for idx, topic in enumerate(topics):
            top = list_top + idx * line_height
            box = (list_left, top, width * 0.75, top + 110)
            draw.rounded_rectangle(box, radius=24, fill=colors[idx % len(colors)])
            draw.text(
                (list_left + 30, top + 28),
                f"{idx + 1}. {topic}",
                font=topic_font,
                fill=(15, 20, 35),
            )

        avatar_box = (width - 360, height - 300, width - 80, height - 80)
        draw.rounded_rectangle(avatar_box, radius=42, fill=(255, 255, 255, 18), outline=(180, 200, 255, 80), width=4)
        draw.ellipse(
            (
                avatar_box[0] + 50,
                avatar_box[1] + 30,
                avatar_box[0] + 210,
                avatar_box[1] + 190,
            ),
            fill=(255, 255, 255, 32),
        )
        draw.text(
            (avatar_box[0] + 110, avatar_box[1] + 210),
            "AI",
            font=subtitle_font,
            fill=(225, 235, 255),
            anchor="mm",
        )
        draw.text(
            (avatar_box[0] + 110, avatar_box[1] + 250),
            "解説中",
            font=small_font,
            fill=(225, 235, 255),
            anchor="mm",
        )

        img.save(output_path, format="PNG")

    def _draw_gradient_background(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        for y in range(height):
            ratio = y / height
            r = int(12 + 30 * ratio)
            g = int(18 + 60 * ratio)
            b = int(45 + 120 * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

        draw.ellipse((-180, -120, width * 0.45, height * 0.8), fill=(120, 180, 255, 40))
        draw.ellipse((width * 0.4, -60, width * 1.2, height * 0.9), fill=(120, 220, 200, 35))

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        custom = self._settings.default_font_path
        if custom and Path(custom).is_file():
            try:
                return ImageFont.truetype(str(custom), size=size)
            except OSError:
                pass

        for candidate in [
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]:
            if Path(candidate).is_file():
                try:
                    return ImageFont.truetype(candidate, size=size)
                except OSError:
                    continue

        return ImageFont.load_default()
