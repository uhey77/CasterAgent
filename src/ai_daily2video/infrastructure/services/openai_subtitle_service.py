from __future__ import annotations

import math
from datetime import timedelta

from ...core.openai_client import get_openai_client
from ...core.settings import get_settings
from ...domain.interfaces import SubtitleGenerator
from ...domain.models import AudioAsset, Script, SubtitleFile, SubtitleSegment


def _format_timestamp(seconds: float) -> str:
    ms = int(seconds * 1000)
    td = timedelta(milliseconds=ms)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = ms % 1000
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


class OpenAISubtitleService(SubtitleGenerator):
    def __init__(self) -> None:
        self._client = get_openai_client()
        self._settings = get_settings()

    def generate_subtitles(self, script: Script, audio: AudioAsset) -> SubtitleFile:
        with audio.file_path.open("rb") as handle:
            response = self._client.audio.transcriptions.create(
                model="whisper-1",
                file=handle,
                response_format="verbose_json",
                temperature=0,
            )
        segments: list[SubtitleSegment] = []
        for chunk in response.segments:
            start = float(chunk.start if hasattr(chunk, 'start') else 0.0)
            end = float(chunk.end if hasattr(chunk, 'end') else start + 2.0)
            text = chunk.text.strip() if hasattr(chunk, 'text') else ""
            if not text:
                continue
            segments.append(SubtitleSegment(start_seconds=start, end_seconds=end, text=text))

        if not segments:
            # fall back to naive equally spaced segments from script
            lines = [line.text for line in script.lines]
            if not lines:
                lines = [script.raw_text]
            duration = max(audio.duration_seconds, len(lines) * 3)
            interval = duration / max(len(lines), 1)
            segments = [
                SubtitleSegment(
                    start_seconds=i * interval,
                    end_seconds=min((i + 1) * interval, duration),
                    text=line,
                )
                for i, line in enumerate(lines)
            ]

        subtitle_path = self._settings.storage.subtitles_dir / f"{audio.article_id}.srt"
        with subtitle_path.open("w", encoding="utf-8") as handle:
            for index, segment in enumerate(segments, start=1):
                handle.write(f"{index}\n")
                handle.write(
                    f"{_format_timestamp(segment.start_seconds)} --> {_format_timestamp(segment.end_seconds)}\n"
                )
                handle.write(f"{segment.text}\n\n")

        return SubtitleFile(article_id=audio.article_id, file_path=subtitle_path, segments=segments)
