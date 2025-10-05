from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass(slots=True)
class Article:
    article_id: int
    title: str
    markdown_body: str
    category: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    url: Optional[str] = None
    published_at: Optional[datetime] = None


@dataclass(slots=True)
class ScriptLine:
    speaker: str
    text: str


@dataclass(slots=True)
class Script:
    article_id: int
    lines: List[ScriptLine]
    raw_text: str
    file_path: Optional[Path] = None


@dataclass(slots=True)
class AudioAsset:
    article_id: int
    file_path: Path
    duration_seconds: float


@dataclass(slots=True)
class SubtitleSegment:
    start_seconds: float
    end_seconds: float
    text: str


@dataclass(slots=True)
class SubtitleFile:
    article_id: int
    file_path: Path
    segments: List[SubtitleSegment]


@dataclass(slots=True)
class GeneratedImage:
    article_id: int
    file_path: Path


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
    tags: List[str]
    category_id: str = "28"
    privacy_status: str = "public"
    language: str = "ja"
    file_path: Optional[Path] = None


@dataclass(slots=True)
class PipelineStatus:
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    notes: List[str] = field(default_factory=list)


class PipelineError(RuntimeError):
    def __init__(self, step: str, message: str) -> None:
        super().__init__(f"Pipeline step '{step}' failed: {message}")
        self.step = step
        self.message = message
