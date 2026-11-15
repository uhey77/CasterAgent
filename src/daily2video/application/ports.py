from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from ..domain.models import Article, AudioAsset, Script, SubtitleFile, VideoAsset, VideoMetadata


class ScriptGenerator(Protocol):
    def build_script(self, article: Article) -> Script: ...


class AudioSynthesizer(Protocol):
    def synthesize(self, script: Script) -> AudioAsset: ...


class SubtitleGenerator(Protocol):
    def generate_subtitles(self, script: Script, audio: AudioAsset) -> SubtitleFile: ...


class MetadataGenerator(Protocol):
    def build_metadata(self, article: Article, script: Script) -> VideoMetadata: ...


class VideoComposer(Protocol):
    def compose(self, audio: AudioAsset, subtitles: SubtitleFile) -> VideoAsset: ...


class ThumbnailGenerator(Protocol):
    def generate(self, article: Article, metadata: VideoMetadata, script: Script | None = None) -> Path: ...


class VideoPublisher(Protocol):
    def publish(self, video: VideoAsset, metadata: VideoMetadata) -> str | None:
        """動画を公開し、公開先の動画IDを返す。公開しなかった場合は None。"""
        ...


class MetadataStore(Protocol):
    def save(self, metadata: VideoMetadata) -> None:
        """変更後のメタデータを保存先へ反映する。"""
        ...


class UploadHistory(Protocol):
    """「1日1本」を守るための投稿済み記録。"""

    def has_uploaded_on(self, day: date) -> bool: ...

    def mark_uploaded(self, day: date) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime:
        """日本時間の現在時刻（タイムゾーン付き）。"""
        ...


class PipelineLogger(Protocol):
    def log(self, payload: dict) -> None: ...

    def bulk_log(self, payloads: Iterable[dict]) -> None: ...


class Notifier(Protocol):
    def notify(self, message: str, *, level: str = "info", extra: dict | None = None) -> None: ...
