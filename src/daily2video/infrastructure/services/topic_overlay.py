from __future__ import annotations

import json
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from ...core.settings import AppSettings
from ...domain.models import SubtitleSegment


@dataclass
class TopicOverlaySpec:
    image_path: Path
    start: float
    end: float


def build_topic_overlay(
    settings: AppSettings,
    article_id: int,
    segments: Sequence[SubtitleSegment],
    total_duration: float,
) -> Optional[TopicOverlaySpec]:
    script_text = _load_script_text(settings, article_id)
    article_text = _load_article_markdown(settings, article_id)
    if not script_text and not article_text:
        return None

    research_items = _extract_research_items(script_text or "", article_text)
    if not research_items:
        return None

    image_path = _create_topic_list_image(settings, article_id, research_items)
    if image_path is None:
        return None

    start, end = _calculate_topic_overlay_window(segments, total_duration)
    return TopicOverlaySpec(image_path=image_path, start=start, end=end)


def overlay_topic_image(
    input_video: Path,
    spec: TopicOverlaySpec,
    output_video: Path,
    total_duration: float,
) -> None:
    width, height = _probe_video_dimensions(input_video)
    overlay_start = max(0.0, min(total_duration, spec.start))
    overlay_end = max(overlay_start, min(total_duration, spec.end))
    y_offset = 0
    x_expr = "(main_w-overlay_w)/2"
    y_expr = f"{y_offset} + (main_h-overlay_h)/2"
    filter_complex = (
        f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease"
        f",pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x00000000"
        "[overlay_src];"
        f"[0:v][overlay_src]overlay={x_expr}:{y_expr}:"
        f"enable='between(t,{overlay_start},{overlay_end})'"
    )

    base_cmd = [
        "ffmpeg",
        "-i",
        str(input_video),
        "-i",
        str(spec.image_path),
        "-filter_complex",
        filter_complex,
        "-c:a",
        "copy",
        "-y",
        str(output_video),
    ]

    codec_variants = [
        ["-c:v", "h264_videotoolbox", "-b:v", "4000k", "-pix_fmt", "yuv420p"],
        ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"],
    ]

    last_error: subprocess.CalledProcessError | None = None
    for variant in codec_variants:
        cmd = base_cmd[:]
        cmd[7:7] = variant
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            continue

    if last_error is not None:
        raise RuntimeError(
            "FFmpeg overlay failed: %s" % (last_error.stderr or last_error.stdout)
        ) from last_error


def _probe_video_dimensions(video_path: Path) -> Tuple[int, int]:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(video_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        for stream in streams:
            width = int(stream.get("width", 0))
            height = int(stream.get("height", 0))
            if width > 0 and height > 0:
                return width, height
    except (subprocess.CalledProcessError, json.JSONDecodeError, ValueError):
        pass
    return 1920, 1080


def _load_script_text(settings: AppSettings, article_id: int) -> Optional[str]:
    script_path = settings.storage.scripts_dir / f"{article_id}.txt"
    if not script_path.exists():
        return None
    try:
        return script_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return script_path.read_text(encoding="utf-8", errors="ignore")


def _load_article_markdown(settings: AppSettings, article_id: int) -> Optional[str]:
    article_path = settings.storage.articles_dir / f"{article_id}.md"
    if not article_path.exists():
        return None
    try:
        return article_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return article_path.read_text(encoding="utf-8", errors="ignore")


def _create_topic_list_image(
    settings: AppSettings,
    article_id: int,
    research_items: List[Tuple[str, str]],
) -> Optional[Path]:
    try:
        img_width, img_height = 1920, 1080
        img = Image.new("RGBA", (img_width, img_height), (255, 255, 255, 242))
        draw = ImageDraw.Draw(img)

        font_path = _get_font_path()

        left_margin = 100
        right_margin = 100
        title_y = 60
        start_y = 220
        bottom_margin = 80
        available_height = img_height - start_y - bottom_margin
        max_columns = min(4, max(1, len(research_items)))

        def load_fonts(scale: float) -> dict[str, ImageFont.FreeTypeFont]:
            title_size = max(32, int(70 * scale))
            number_size = max(24, int(42 * scale))
            text_size = max(20, int(36 * scale))
            return {
                "title": ImageFont.truetype(font_path, title_size),
                "number": ImageFont.truetype(font_path, number_size),
                "text": ImageFont.truetype(font_path, text_size),
            }

        def layout_fits(
            items: List[Tuple[str, str]],
            columns: int,
            column_width: int,
            fonts: dict[str, ImageFont.FreeTypeFont],
            base_spacing: int,
            number_offset: int,
            line_height: int,
        ) -> bool:
            if column_width - number_offset <= 40:
                return False

            items_per_column = math.ceil(len(items) / columns)
            for col_idx in range(columns):
                start_index = col_idx * items_per_column
                end_index = min(start_index + items_per_column, len(items))
                column_items = items[start_index:end_index]
                current_height = 0

                for item_pos, (_, title) in enumerate(column_items):
                    wrapped_lines = _wrap_text(title, fonts["text"], column_width - number_offset)
                    lines_count = max(1, len(wrapped_lines))
                    item_height = max(fonts["number"].size, lines_count * line_height)
                    current_height += item_height
                    if item_pos < len(column_items) - 1:
                        current_height += base_spacing

                    if current_height > available_height:
                        return False

            return True

        selected_layout: Optional[
            tuple[dict[str, ImageFont.FreeTypeFont], int, int, int, int, int, int]
        ] = None

        min_column_width = 420 if len(research_items) <= 8 else 360
        for scale in (1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6):
            fonts = load_fonts(scale)
            base_spacing = max(12, int(20 * scale))
            gutter = max(40, int(60 * scale))
            line_height = fonts["text"].size + max(6, int(8 * scale))
            number_offset = max(40, int(fonts["number"].size * 1.4))

            for column_count in range(max_columns, 0, -1):
                total_gutter = gutter * (column_count - 1)
                available_width = img_width - left_margin - right_margin - total_gutter
                if available_width <= column_count * 60:
                    continue
                column_width = int(available_width / column_count)
                if column_width < min_column_width:
                    continue

                if layout_fits(
                    research_items,
                    column_count,
                    column_width,
                    fonts,
                    base_spacing,
                    number_offset,
                    line_height,
                ):
                    selected_layout = (
                        fonts,
                        column_count,
                        column_width,
                        gutter,
                        number_offset,
                        base_spacing,
                        line_height,
                    )
                    break

            if selected_layout:
                break

        if not selected_layout:
            fonts = load_fonts(0.6)
            min_column_width = 360
            gutter = max(40, int(60 * 0.6))
            column_count = 1
            column_width = img_width - left_margin - right_margin
            for candidate in range(max_columns, 0, -1):
                total_gutter = gutter * (candidate - 1)
                available_width = img_width - left_margin - right_margin - total_gutter
                if available_width <= 0:
                    continue
                candidate_width = int(available_width / candidate)
                if candidate_width >= min_column_width:
                    column_count = candidate
                    column_width = candidate_width
                    break
            number_offset = max(40, int(fonts["number"].size * 1.4))
            base_spacing = max(12, int(20 * 0.6))
            line_height = fonts["text"].size + max(6, int(8 * 0.6))
            selected_layout = (
                fonts,
                column_count,
                column_width,
                gutter,
                number_offset,
                base_spacing,
                line_height,
            )

        fonts, column_count, column_width, gutter, number_offset, base_spacing, line_height = selected_layout

        title_text = f"本日のトピック（全{len(research_items)}項目）"
        draw.text((left_margin, title_y), title_text, font=fonts["title"], fill=(31, 42, 68))

        column_positions: List[int] = []
        for col_idx in range(column_count):
            column_positions.append(left_margin + col_idx * (column_width + gutter))

        items_per_column = math.ceil(len(research_items) / column_count)
        for col_idx in range(column_count):
            start_index_col = col_idx * items_per_column
            end_index_col = min(start_index_col + items_per_column, len(research_items))
            column_items = research_items[start_index_col:end_index_col]

            current_y = start_y
            for row_idx, (_, title) in enumerate(column_items):
                item_index = start_index_col + row_idx + 1
                draw.text(
                    (column_positions[col_idx], current_y),
                    f"{item_index}.",
                    font=fonts["number"],
                    fill=(30, 136, 229),
                )

                text_x = column_positions[col_idx] + number_offset
                wrapped_lines = _wrap_text(title, fonts["text"], column_width - number_offset)
                if not wrapped_lines:
                    wrapped_lines = [""]

                for line_idx, line in enumerate(wrapped_lines):
                    draw.text(
                        (text_x, current_y + line_idx * line_height),
                        line,
                        font=fonts["text"],
                        fill=(33, 33, 33),
                    )

                lines_count = max(1, len(wrapped_lines))
                item_height = max(fonts["number"].size, lines_count * line_height)
                current_y += item_height
                if row_idx < len(column_items) - 1:
                    current_y += base_spacing

        output_path = settings.storage.images_dir / f"{article_id}_topics.png"
        img.save(str(output_path))
        return output_path

    except Exception:
        return None


def _calculate_topic_overlay_window(
    segments: Sequence[SubtitleSegment],
    total_duration: float,
) -> Tuple[float, float]:
    start_keywords = [
        "ハイライト",
        "今日のハイライト",
        "本日のハイライト",
        "今日のトピック",
        "本日のトピック",
        "詳しくは画像",
        "目次画像",
    ]
    end_keywords = [
        "今日のトピック",
        "本日のトピック",
        "項目あります",
        "分野では",
        "最初の研究",
        "1つ目",
        "一つ目",
    ]

    overlay_start: Optional[float] = None
    overlay_end: Optional[float] = None

    for segment in segments:
        normalized = segment.text.replace("\n", "").replace(" ", "").replace("　", "")

        if overlay_start is None and any(keyword in normalized for keyword in start_keywords):
            overlay_start = segment.start_seconds
            continue

        if overlay_start is not None:
            if any(keyword in normalized for keyword in end_keywords):
                overlay_end = segment.start_seconds
                break
            if normalized.startswith("1") or normalized.startswith("１"):
                overlay_end = segment.start_seconds
                break

    if overlay_start is None:
        overlay_start = 0.0

    if overlay_end is None:
        overlay_end = min(total_duration, overlay_start + 12.0)

    if overlay_end < overlay_start:
        overlay_end = overlay_start

    return overlay_start, overlay_end


def _extract_research_items(script_text: str, article_text: Optional[str]) -> List[Tuple[str, str]]:
    seen: set[str] = set()

    if article_text:
        items_from_article = _extract_items_from_article(article_text, seen)
        if items_from_article:
            return items_from_article

    items: List[Tuple[str, str]] = []
    seen = set()

    for line in script_text.splitlines():
        matches_jp = re.findall(r"「([^」]+)」", line)
        matches_md = re.findall(r"\*\*([^*]+)\*\*", line)
        matches = matches_jp + matches_md

        for match in matches:
            title = match.strip()
            if not title or len(title) < 3 or title.isdigit() or title in seen:
                continue

            skip_phrases = [
                "AI Daily",
                "こちら",
                "まず",
                "次に",
                "最後に",
                "さらに",
                "Bridge",
                "GRPO",
                "M2PO",
                "HuDiff",
            ]
            if any(phrase == title for phrase in skip_phrases):
                continue

            category = _categorize_research(title, line)
            items.append((category, title))
            seen.add(title)

            if len(items) >= 20:
                break

        if len(items) >= 20:
            break

    return items


def _extract_items_from_article(article_text: str, seen: set[str]) -> List[Tuple[str, str]]:
    items: List[Tuple[str, str]] = []
    current_section = ""

    for raw_line in article_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("#"):
            hashes = len(line) - len(line.lstrip("#"))
            content = line[hashes:].strip()
            if hashes <= 3:
                current_section = content
                continue

            title = re.sub(r"^\d+\)\s*", "", content).strip()
            if not title or title in seen:
                continue
            category = _categorize_research(title, current_section or raw_line)
            items.append((category, title))
            seen.add(title)
            continue

        match = re.match(r"^\d+\)\s*\*\*([^*]+)\*\*", line)
        if match:
            title = match.group(1).strip()
            if not title or title in seen:
                continue
            category = _categorize_research(title, current_section or raw_line)
            items.append((category, title))
            seen.add(title)
            continue

        match = re.match(r"^\*\*([^*]+)\*\*", line)
        if match:
            title = match.group(1).strip()
            if not title or title in seen:
                continue
            category = _categorize_research(title, current_section or raw_line)
            items.append((category, title))
            seen.add(title)

        if len(items) >= 20:
            break

    return items


def _categorize_research(title: str, line: str) -> str:
    line_lower = line.lower()
    title_lower = title.lower()

    if any(keyword in line_lower or keyword in title_lower for keyword in [
        "xai",
        "explainable",
        "interpretability",
        "activation",
        "deactivation",
        "eap",
        "textcam",
        "edct",
    ]):
        return "XAI"

    if any(keyword in line_lower or keyword in title_lower for keyword in [
        "llm",
        "エージェント",
        "agent",
        "rlhf",
        "grpo",
        "dpo",
        "policy",
        "m2po",
        "sirl",
    ]):
        return "LLM"

    if any(keyword in line_lower or keyword in title_lower for keyword in [
        "生成",
        "diffusion",
        "generation",
        "temporal",
        "score",
        "flow",
        "bridge",
    ]):
        return "生成AI"

    if any(keyword in line_lower or keyword in title_lower for keyword in [
        "science",
        "nature",
        "bio",
        "antibod",
        "protein",
        "hudiff",
        "dna",
    ]):
        return "Science"

    if "ウォッチ" in line or "watch" in line_lower or "rlad" in title_lower or "bbon" in title_lower or "executable" in title_lower:
        return "X"

    return ""


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    if max_width <= 0:
        return [text]

    tokens = re.split(r"(\s+)", text)
    lines: List[str] = []
    current_line = ""

    def flush_line() -> None:
        nonlocal current_line
        trimmed = current_line.rstrip()
        lines.append(trimmed if trimmed else "")
        current_line = ""

    def append_fragment(fragment: str) -> None:
        nonlocal current_line
        if not fragment:
            return

        tentative = current_line + fragment
        if not current_line or _measure_text(tentative, font) <= max_width:
            current_line = tentative
            return

        flush_line()
        if _measure_text(fragment, font) <= max_width:
            current_line = fragment.lstrip()
            return

        for char in fragment:
            tentative = current_line + char
            if not current_line or _measure_text(tentative, font) <= max_width:
                current_line = tentative
            else:
                flush_line()
                current_line = char if not char.isspace() else ""

    for token in tokens:
        append_fragment(token)

    if current_line:
        flush_line()

    return lines or [""]


def _measure_text(text: str, font: ImageFont.FreeTypeFont) -> float:
    try:
        return font.getlength(text)
    except AttributeError:
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]


def _get_font_path() -> str:
    font_candidates = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/ee89e7987a76cc8cfdff36c96bd7bc77655b343e.asset/AssetData/YuGothic-Medium.otf",
    ]

    for font in font_candidates:
        if Path(font).exists():
            return font

    return "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc"
