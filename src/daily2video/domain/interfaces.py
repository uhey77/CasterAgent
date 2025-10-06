from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Protocol

from .models import (
    Article,
    AudioAsset,
    GeneratedImage,
    Script,
    SubtitleFile,
    VideoAsset,
    VideoMetadata,
)


class ArticleRepository(Protocol):
    def latest(self) -> Article | None: ...

    def by_id(self, article_id: int) -> Article | None: ...


class ScriptGenerator(Protocol):
    def build_script(self, article: Article) -> Script: ...


class AudioSynthesizer(Protocol):
    def synthesize(self, script: Script) -> AudioAsset: ...


class SubtitleGenerator(Protocol):
    def generate_subtitles(self, script: Script, audio: AudioAsset) -> SubtitleFile: ...


class MetadataGenerator(Protocol):
    def build_metadata(self, article: Article, script: Script) -> VideoMetadata: ...


class BackgroundImageGenerator(Protocol):
    def create_image(self, article: Article) -> GeneratedImage: ...


class VideoComposer(Protocol):
    def compose(self, audio: AudioAsset, subtitles: SubtitleFile, background: GeneratedImage) -> VideoAsset: ...


class VideoPublisher(Protocol):
    def publish(self, video: VideoAsset, metadata: VideoMetadata) -> str | None: ...


class PipelineLogger(Protocol):
    def log(self, payload: dict) -> None: ...

    def bulk_log(self, payloads: Iterable[dict]) -> None: ...


class Notifier(Protocol):
    def notify(self, message: str, *, level: str = "info", extra: dict | None = None) -> None: ...
