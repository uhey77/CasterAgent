from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional
import tempfile

import pytest

from daily2video.application.use_cases.generate_daily_video import (
    GenerateDailyVideo,
    GenerateDailyVideoInput,
    _now_jst,
)
from daily2video.domain.interfaces import (
    ArticleRepository,
    AudioSynthesizer,
    MetadataGenerator,
    Notifier,
    PipelineLogger,
    ScriptGenerator,
    SubtitleGenerator,
    VideoComposer,
    VideoPublisher,
)
from daily2video.domain.models import (
    Article,
    AudioAsset,
    DialogueSegment,
    PipelineError,
    Script,
    ScriptLine,
    SubtitleFile,
    SubtitleSegment,
    VideoAsset,
    VideoMetadata,
)
from daily2video.core.settings import StoragePaths


class FakeArticleRepo(ArticleRepository):
    def __init__(self, article: Optional[Article]) -> None:
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


class MemoryLogger(PipelineLogger):
    def __init__(self) -> None:
        self.events: list[dict] = []

    def log(self, payload: dict) -> None:
        self.events.append(payload)

    def bulk_log(self, payloads: Iterable[dict]) -> None:
        for payload in payloads:
            self.log(payload)


class MemoryNotifier(Notifier):
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def notify(self, message: str, *, level: str = "info", extra: Optional[dict] = None) -> None:
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


def build_use_case(article: Optional[Article]) -> tuple[GenerateDailyVideo, MemoryNotifier]:
    storage_root = Path(tempfile.mkdtemp(prefix="ai-daily-test-"))
    storage = StoragePaths(root=storage_root)
    storage.ensure_directories()
    notifier = MemoryNotifier()
    use_case = GenerateDailyVideo(
        article_repo=FakeArticleRepo(article),
        script_generator=FakeScriptGenerator(),
        audio_synthesizer=FakeAudioSynthesizer(),
        subtitle_generator=FakeSubtitleGenerator(),
        metadata_generator=FakeMetadataGenerator(),
        video_composer=FakeVideoComposer(),
        publisher=FakePublisher(),
        logger=MemoryLogger(),
        notifier=notifier,
        storage=storage,
    )
    return use_case, notifier


def test_generate_daily_video_success(sample_article: Article) -> None:
    use_case, notifier = build_use_case(sample_article)
    result = use_case.execute(GenerateDailyVideoInput())

    assert result.status.status == "uploaded"
    assert result.video and result.video.file_path.name == "video.mp4"
    assert result.metadata and result.metadata.title.startswith("AI Daily—")
    assert _now_jst().strftime("%Y-%m-%d") in result.metadata.title
    assert result.youtube_video_id == "youtube-video-id"
    assert len(notifier.messages) == 1

    # 次の実行ではアップロードがスキップされること
    result_second = use_case.execute(GenerateDailyVideoInput())
    assert result_second.status.status == "video_saved"
    assert result_second.youtube_video_id is None
    assert len(notifier.messages) == 1  # 通知は増えない


def test_generate_daily_video_missing_article() -> None:
    use_case, _ = build_use_case(None)
    with pytest.raises(PipelineError):
        use_case.execute(GenerateDailyVideoInput())


def test_should_upload_video_allows_past_date(sample_article: Article) -> None:
    use_case, _ = build_use_case(sample_article)
    sample_article.published_at = datetime.now(timezone.utc) - timedelta(days=2)
    should_upload, reason = use_case._should_upload_video(sample_article, None)  # pylint: disable=protected-access
    assert should_upload
    assert reason is None


def test_should_upload_video_blocks_future_date(sample_article: Article) -> None:
    use_case, _ = build_use_case(sample_article)
    sample_article.published_at = datetime.now(timezone.utc) + timedelta(days=1)
    should_upload, reason = use_case._should_upload_video(sample_article, None)  # pylint: disable=protected-access
    assert not should_upload
    assert reason == "article_date_in_future"


def test_should_upload_video_allows_when_title_matches_today(sample_article: Article) -> None:
    use_case, _ = build_use_case(sample_article)
    now_jst = _now_jst()
    sample_article.published_at = now_jst + timedelta(days=1)
    today_str = now_jst.strftime("%Y-%m-%d")
    metadata = VideoMetadata(
        article_id=sample_article.article_id,
        title=f"AI Daily—{today_str}",
        description="desc",
        tags=[],
        category_id="28",
        privacy_status="public",
    )
    should_upload, reason = use_case._should_upload_video(sample_article, metadata)  # pylint: disable=protected-access
    assert should_upload
    assert reason is None
