from __future__ import annotations

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
    if not script_text:
        return None

    research_items = _extract_research_items(script_text)
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
    overlay_start = max(0.0, min(total_duration, spec.start))
    overlay_end = max(overlay_start, min(total_duration, spec.end))
    subtitle_safe_area = 240
    y_offset = 80
    available_height = max(200, int(1080 - y_offset - subtitle_safe_area))

    cmd = [
        "ffmpeg",
        "-i",
        str(input_video),
        "-i",
        str(spec.image_path),
        "-filter_complex",
        (
            "[1:v] scale=1920:{available_height}:force_original_aspect_ratio=decrease [topic]; "
            "[0:v][topic] overlay=(main_w-overlay_w)/2:{y_offset}:"
            "enable='between(t,{start},{end})'"
        ).format(
            available_height=available_height,
            y_offset=y_offset,
            start=overlay_start,
            end=overlay_end,
        ),
        "-c:a",
        "copy",
        "-y",
        str(output_video),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "FFmpeg overlay failed: %s" % (exc.stderr or exc.stdout)
        ) from exc


def _load_script_text(settings: AppSettings, article_id: int) -> Optional[str]:
    script_path = settings.storage.scripts_dir / f"{article_id}.txt"
    if not script_path.exists():
        return None
    try:
        return script_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return script_path.read_text(encoding="utf-8", errors="ignore")


def _create_topic_list_image(
    settings: AppSettings,
    article_id: int,
    research_items: List[Tuple[str, str]],
) -> Optional[Path]:
    try:
        img = Image.new("RGBA", (1920, 1080), (255, 255, 255, 242))
        draw = ImageDraw.Draw(img)

        font_path = _get_font_path()
        title_font = ImageFont.truetype(font_path, 70)
        number_font = ImageFont.truetype(font_path, 42)
        text_font = ImageFont.truetype(font_path, 36)

        title_text = f"本日のトピック（全{len(research_items)}項目）"
        draw.text((100, 60), title_text, font=title_font, fill=(31, 42, 68))

        column_count = 2
        column_width = 720
        column_x_positions = [100, 980]
        start_y = 220
        base_line_spacing = 20

        items_per_column = math.ceil(len(research_items) / column_count)
        for col_idx in range(column_count):
            start_index_col = col_idx * items_per_column
            end_index_col = min(start_index_col + items_per_column, len(research_items))
            column_items = research_items[start_index_col:end_index_col]
            current_y = start_y

            for row_idx, (_, title) in enumerate(column_items):
                item_index = start_index_col + row_idx + 1
                draw.text(
                    (column_x_positions[col_idx], current_y),
                    f"{item_index}.",
                    font=number_font,
                    fill=(30, 136, 229),
                )
                text_x = column_x_positions[col_idx] + 60
                wrapped_lines = _wrap_text(title, text_font, column_width)
                line_height = text_font.size + 10

                for line_idx, line in enumerate(wrapped_lines):
                    draw.text(
                        (text_x, current_y + line_idx * line_height),
                        line,
                        font=text_font,
                        fill=(33, 33, 33),
                    )

                item_height = max(number_font.size, len(wrapped_lines) * line_height)
                current_y += item_height + base_line_spacing

        output_path = settings.storage.images_dir / f"{article_id}_topics.png"
        img.save(str(output_path))
        return output_path

    except Exception:
        return None


def _calculate_topic_overlay_window(
    segments: Sequence[SubtitleSegment],
    total_duration: float,
) -> Tuple[float, float]:
    start_keywords = ["ハイライト", "今日のハイライト", "本日のハイライト"]
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


def _extract_research_items(script_text: str) -> List[Tuple[str, str]]:
    items: List[Tuple[str, str]] = []
    seen: set[str] = set()

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
    lines: List[str] = []
    current_line = ""

    for char in text:
        tentative = current_line + char
        if _measure_text(tentative, font) <= max_width:
            current_line = tentative
        else:
            if current_line:
                lines.append(current_line)
            current_line = char

    if current_line:
        lines.append(current_line)

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
