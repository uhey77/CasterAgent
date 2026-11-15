from __future__ import annotations

import tempfile
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from daily2video.application.ports import (
    AudioSynthesizer,
    Clock,
    MetadataGenerator,
    MetadataStore,
    Notifier,
    PipelineLogger,
    ScriptGenerator,
    SubtitleGenerator,
    ThumbnailGenerator,
    UploadHistory,
    VideoComposer,
    VideoPublisher,
)
from daily2video.application.use_cases.generate_daily_video import (
    GenerateDailyVideo,
    GenerateDailyVideoInput,
)
from daily2video.domain.errors import ArticleNotFoundError, PipelineError
from daily2video.domain.models import (
    JST,
    Article,
    AudioAsset,
    DialogueSegment,
    PipelineStage,
    Script,
    ScriptLine,
    SubtitleFile,
    SubtitleSegment,
    VideoAsset,
    VideoMetadata,
)
from daily2video.domain.repositories import ArticleRepository

NOW = datetime(2026, 11, 15, 9, 0, tzinfo=JST)


class FakeArticleRepo(ArticleRepository):
    def __init__(self, article: Article | None) -> None:
        self._article = article

    def latest(self) -> Article | None:
        return self._article

    def by_id(self, article_id: int) -> Article | None:
        if self._article and self._article.article_id == article_id:
            return self._article
        return None


class FakeScriptGenerator(ScriptGenerator):
    def build_script(self, article: Article) -> Script:
        return Script(
            article_id=article.article_id,
            raw_text="こんにちは\nこんばんは",
            lines=[
                ScriptLine("Narrator", "こんにちは"),
                ScriptLine("Narrator", "こんばんは"),
            ],
            file_path=Path("/tmp/script.txt"),
        )


class FakeAudioSynthesizer(AudioSynthesizer):
    def synthesize(self, script: Script) -> AudioAsset:
        segments = [
            DialogueSegment(speaker="Narrator", text="こんにちは", start_seconds=0.0, end_seconds=5.0),
            DialogueSegment(speaker="Narrator", text="こんばんは", start_seconds=5.0, end_seconds=10.0),
        ]
        return AudioAsset(
            article_id=script.article_id,
            file_path=Path("/tmp/audio.mp3"),
            duration_seconds=10.0,
            segments=segments,
        )


class FakeSubtitleGenerator(SubtitleGenerator):
    def generate_subtitles(self, script: Script, audio: AudioAsset) -> SubtitleFile:
        return SubtitleFile(
            article_id=script.article_id,
            file_path=Path("/tmp/subtitles.srt"),
            segments=[SubtitleSegment(0.0, 2.0, "こんにちは"), SubtitleSegment(2.0, 4.0, "こんばんは")],
        )


class FakeMetadataGenerator(MetadataGenerator):
    def build_metadata(self, article: Article, script: Script) -> VideoMetadata:
        return VideoMetadata(
            article_id=article.article_id,
            title="AI Daily ニュース",
            description="説明",
            tags=["AI"],
            category_id="28",
            privacy_status="public",
            file_path=Path("/tmp/meta.json"),
        )


class FakeVideoComposer(VideoComposer):
    def compose(self, audio: AudioAsset, subtitles: SubtitleFile) -> VideoAsset:
        return VideoAsset(article_id=audio.article_id, file_path=Path("/tmp/video.mp4"), duration_seconds=audio.duration_seconds)


class FakePublisher(VideoPublisher):
    def publish(self, video: VideoAsset, metadata: VideoMetadata) -> str | None:
        return "youtube-video-id"


class FakeThumbnailGenerator(ThumbnailGenerator):
    def generate(self, article: Article, metadata: VideoMetadata, script: Script | None = None) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="thumb-"))
        temp_dir.mkdir(parents=True, exist_ok=True)
        path = temp_dir / "thumb.png"
        path.write_text("thumbnail")
        return path


class MemoryLogger(PipelineLogger):
    def __init__(self) -> None:
        self.events: list[dict] = []

    def log(self, payload: dict) -> None:
        self.events.append(payload)

    def bulk_log(self, payloads: Iterable[dict]) -> None:
        for payload in payloads:
            self.log(payload)


class MemoryMetadataStore(MetadataStore):
    def __init__(self) -> None:
        self.saved_titles: list[str] = []

    def save(self, metadata: VideoMetadata) -> None:
        self.saved_titles.append(metadata.title)


class MemoryUploadHistory(UploadHistory):
    def __init__(self) -> None:
        self.days: set[date] = set()

    def has_uploaded_on(self, day: date) -> bool:
        return day in self.days

    def mark_uploaded(self, day: date) -> None:
        self.days.add(day)


class FixedClock(Clock):
    def __init__(self, now: datetime = NOW) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current


class MemoryNotifier(Notifier):
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def notify(self, message: str, *, level: str = "info", extra: dict | None = None) -> None:
        self.messages.append((level, message))


@pytest.fixture()
def sample_article() -> Article:
    return Article(
        article_id=123,
        title="最新AIニュース",
        markdown_body="## 見出し",
        category="ai",
        tags=["ai"],
        url="https://example.com",
        published_at=None,
    )


class Harness:
    def __init__(self, article: Article | None, publisher: VideoPublisher | None = None) -> None:
        self.notifier = MemoryNotifier()
        self.logger = MemoryLogger()
        self.metadata_store = MemoryMetadataStore()
        self.upload_history = MemoryUploadHistory()
        self.clock = FixedClock()
        self.use_case = GenerateDailyVideo(
            article_repo=FakeArticleRepo(article),
            script_generator=FakeScriptGenerator(),
            audio_synthesizer=FakeAudioSynthesizer(),
            subtitle_generator=FakeSubtitleGenerator(),
            metadata_generator=FakeMetadataGenerator(),
            video_composer=FakeVideoComposer(),
            thumbnail_generator=FakeThumbnailGenerator(),
            publisher=publisher or FakePublisher(),
            logger=self.logger,
            notifier=self.notifier,
            metadata_store=self.metadata_store,
            upload_history=self.upload_history,
            clock=self.clock,
        )

    def run(self, **kwargs):
        return self.use_case.execute(GenerateDailyVideoInput(**kwargs))

    def events(self) -> list[str]:
        return [payload["event"] for payload in self.logger.events]


def test_generate_daily_video_success(sample_article: Article) -> None:
    harness = Harness(sample_article)
    result = harness.run()

    assert result.status.status is PipelineStage.UPLOADED
    assert result.video and result.video.file_path.name == "video.mp4"
    assert result.metadata and result.metadata.title == "AI Daily—2026-11-15"
    assert result.youtube_video_id == "youtube-video-id"
    assert result.metadata.thumbnail_path is not None
    assert result.metadata.thumbnail_path.exists()
    # タイトル確定時とサムネイル付与時の2回、変更後のメタデータが保存される
    assert harness.metadata_store.saved_titles == ["AI Daily—2026-11-15"] * 2
    assert harness.upload_history.days == {NOW.date()}
    assert len(harness.notifier.messages) == 1

    # 同じ日の次の実行ではアップロードがスキップされること
    result_second = harness.run()
    assert result_second.status.status is PipelineStage.VIDEO_SAVED
    assert result_second.youtube_video_id is None
    assert len(harness.notifier.messages) == 1  # 通知は増えない

    # 日付が変われば再び投稿される
    harness.clock.current = NOW + timedelta(days=1)
    assert harness.run().status.status is PipelineStage.UPLOADED


def test_generate_daily_video_missing_article() -> None:
    harness = Harness(None)
    with pytest.raises(ArticleNotFoundError) as excinfo:
        harness.run()
    assert isinstance(excinfo.value, PipelineError)
    assert harness.events()[-1] == "pipeline_failed"
    assert harness.notifier.messages == [("error", "AI-Daily動画の自動生成でエラーが発生しました")]


def test_future_dated_article_is_saved_but_not_uploaded(sample_article: Article) -> None:
    sample_article.issue_date = NOW.date() + timedelta(days=1)
    harness = Harness(sample_article)

    result = harness.run()

    assert result.status.status is PipelineStage.VIDEO_SAVED
    assert result.video is not None  # 動画自体は生成して残す
    assert result.youtube_video_id is None
    assert harness.upload_history.days == set()
    assert any("未来日" in note for note in result.status.notes)
    skip_event = next(p for p in harness.logger.events if p["event"] == "upload_skipped")
    assert skip_event["reason"] == "article_date_in_future"
    assert skip_event["article_date"] == "2026-11-16"
    assert len(harness.notifier.messages) == 1  # スキップしたことは通知する

    # 記事の日付になれば投稿される
    harness.clock.current = NOW + timedelta(days=1)
    assert harness.run().status.status is PipelineStage.UPLOADED


def test_publisher_without_video_id_keeps_video_saved(sample_article: Article) -> None:
    class LocalOnlyPublisher(VideoPublisher):
        def publish(self, video: VideoAsset, metadata: VideoMetadata) -> str | None:
            return None

    harness = Harness(sample_article, publisher=LocalOnlyPublisher())
    result = harness.run()

    assert result.status.status is PipelineStage.VIDEO_SAVED
    assert harness.upload_history.days == set()  # 投稿していないので記録しない
    assert len(harness.notifier.messages) == 1


def test_force_upload_allows_duplicate_post(sample_article: Article) -> None:
    harness = Harness(sample_article)
    harness.run()

    result_force = harness.run(force_upload=True)

    assert result_force.status.status is PipelineStage.UPLOADED
    assert result_force.youtube_video_id == "youtube-video-id"
    assert len(harness.notifier.messages) == 2  # 強制実行でも通知される
