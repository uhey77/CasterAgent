from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ...core.settings import AppSettings
from ...application.ports import VideoComposer
from ...domain.models import AudioAsset, SubtitleFile, SubtitleSegment, VideoAsset
from .ffmpeg_tools import audio_duration, ffmpeg
from .topic_overlay import build_topic_overlay, overlay_topic_image


class MoviePyVideoComposer(VideoComposer):
    """Compatibility name for the FFmpeg-backed video composer."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def compose(self, audio: AudioAsset, subtitles: SubtitleFile) -> VideoAsset:
        temp_output_path = self._settings.storage.videos_dir / f"{audio.article_id}_temp.mp4"
        final_output_path = self._settings.storage.videos_dir / f"{audio.article_id}.mp4"
        duration = audio_duration(audio.file_path)
        with tempfile.TemporaryDirectory(prefix="daily-video-") as directory:
            caption_images = self._build_subtitle_images(
                subtitles.segments, duration, Path(directory)
            )
            cmd = [
                ffmpeg(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x0f0f14:s=1920x1080:r=30:d={duration}",
                "-i",
                str(audio.file_path),
            ]
            for image, _, _ in caption_images:
                cmd.extend(["-loop", "1", "-i", str(image)])
            filters = []
            previous = "0:v"
            for i, (_, start, end) in enumerate(caption_images):
                output = f"v{i}"
                filters.append(
                    f"[{previous}][{i + 2}:v]overlay=0:880:enable='between(t,{start},{end})'[{output}]"
                )
                previous = output
            if filters:
                cmd.extend(["-filter_complex", ";".join(filters), "-map", f"[{previous}]"])
            else:
                cmd.extend(["-map", "0:v"])
            cmd.extend(
                [
                    "-map",
                    "1:a",
                    "-t",
                    str(duration),
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:v",
                    "4000k",
                    "-threads",
                    "4",
                    str(temp_output_path),
                ]
            )
            subprocess.run(cmd, check=True, capture_output=True, text=True)

        overlay_spec = build_topic_overlay(
            self._settings, audio.article_id, subtitles.segments, duration
        )
        if overlay_spec:
            try:
                overlay_topic_image(temp_output_path, overlay_spec, final_output_path, duration)
                temp_output_path.unlink(missing_ok=True)
            except Exception as exc:
                print(f"トピック画像オーバーレイでエラー: {exc}")
                temp_output_path.rename(final_output_path)
        else:
            temp_output_path.rename(final_output_path)
        return VideoAsset(
            article_id=audio.article_id, file_path=final_output_path, duration_seconds=duration
        )

    def _build_subtitle_images(
        self, segments: list[SubtitleSegment], duration: float, directory: Path
    ):
        font_path = self._get_font()
        if font_path is None:
            print("ERROR: 利用可能な日本語フォントが見つかりません")
            return []
        font = ImageFont.truetype(font_path, 60)
        result = []
        for segment in segments:
            start, end = max(segment.start_seconds, 0.0), min(segment.end_seconds, duration)
            if start >= end:
                continue
            image = Image.new("RGBA", (1920, 200), (0, 0, 0, 204))
            draw = ImageDraw.Draw(image)
            lines = []
            line = ""
            for char in segment.text.replace("\n", " "):
                if line and draw.textlength(line + char, font=font) > 1600:
                    lines.append(line)
                    line = ""
                line += char
            if line:
                lines.append(line)
            text = "\n".join(lines)
            box = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=4)
            width, height = box[2] - box[0], box[3] - box[1]
            draw.multiline_text(
                ((1920 - width) / 2, max(0, (200 - height) / 2) - box[1]),
                text,
                font=font,
                fill="white",
                align="center",
                spacing=4,
            )
            path = directory / f"subtitle-{len(result)}.png"
            image.save(path)
            result.append((path, start, end))
        return result

    def _get_font(self) -> str | None:
        for font in [
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        ]:
            try:
                ImageFont.truetype(font, 20)
                return font
            except OSError:
                continue
        return None
