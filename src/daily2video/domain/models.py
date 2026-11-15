from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path

# 「当日」の判定など、業務上の日付は日本時間で扱う
JST = timezone(timedelta(hours=9))

_TITLE_DATE_PATTERN = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


class PipelineStage(StrEnum):
    """パイプラインの進行状態。"""

    STARTED = "started"
    ARTICLE_READY = "article_ready"
    SCRIPT_READY = "script_ready"
    AUDIO_READY = "audio_ready"
    SUBTITLES_READY = "subtitles_ready"
    METADATA_READY = "metadata_ready"
    THUMBNAIL_READY = "thumbnail_ready"
    VIDEO_READY = "video_ready"
    VIDEO_SAVED = "video_saved"
    UPLOADED = "uploaded"
    FAILED = "failed"


class UploadSkipReason(StrEnum):
    """YouTubeへのアップロードを見送る理由。"""

    ALREADY_UPLOADED_TODAY = "already_uploaded_today"
    ARTICLE_DATE_IN_FUTURE = "article_date_in_future"


@dataclass(slots=True)
class Article:
    article_id: int
    title: str
    markdown_body: str
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    url: str | None = None
    published_at: datetime | None = None
    # 記事が対象とする日付（記事名に書かれた日付）。公開時刻とは別物。
    issue_date: date | None = None

    def effective_date(self) -> date | None:
        """記事がいつの分かを表す日付。記事名の日付を優先し、無ければ公開日（日本時間）。"""
        if self.issue_date:
            return self.issue_date
        if not self.published_at:
            return None
        if self.published_at.tzinfo:
            return self.published_at.astimezone(JST).date()
        return self.published_at.date()


@dataclass(slots=True)
class ScriptLine:
    speaker: str
    text: str


@dataclass(slots=True)
class Script:
    article_id: int
    lines: list[ScriptLine]
    raw_text: str
    file_path: Path | None = None


@dataclass(slots=True)
class DialogueSegment:
    speaker: str
    text: str
    start_seconds: float
    end_seconds: float


@dataclass(slots=True)
class AudioAsset:
    article_id: int
    file_path: Path
    duration_seconds: float
    segments: list[DialogueSegment] = field(default_factory=list)


@dataclass(slots=True)
class SubtitleSegment:
    start_seconds: float
    end_seconds: float
    text: str


@dataclass(slots=True)
class SubtitleFile:
    article_id: int
    file_path: Path
    segments: list[SubtitleSegment]


@dataclass(slots=True)
class VideoAsset:
    article_id: int
    file_path: Path
    duration_seconds: float


@dataclass(slots=True)
class VideoMetadata:
    article_id: int
    title: str
    description: str
    tags: list[str]
    category_id: str = "28"
    privacy_status: str = "public"
    language: str = "ja"
    thumbnail_path: Path | None = None
    file_path: Path | None = None

    def apply_daily_title(self, day: date) -> None:
        """動画タイトルは配信日を含む定型に統一する。"""
        self.title = f"AI Daily—{day.isoformat()}"

    def title_date(self) -> date | None:
        """タイトルに含まれる日付（YYYY-MM-DD）。無ければ None。"""
        if not self.title:
            return None
        match = _TITLE_DATE_PATTERN.search(self.title)
        if not match:
            return None
        try:
            year, month, day = map(int, match.groups())
            return date(year, month, day)
        except ValueError:
            return None


@dataclass(slots=True)
class PipelineStatus:
    status: PipelineStage
    started_at: datetime
    completed_at: datetime | None = None
    notes: list[str] = field(default_factory=list)
