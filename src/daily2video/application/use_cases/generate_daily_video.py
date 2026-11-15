from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ...domain.errors import ArticleNotFoundError
from ...domain.models import (
    Article,
    PipelineStage,
    PipelineStatus,
    Script,
    UploadSkipReason,
    VideoAsset,
    VideoMetadata,
)
from ...domain.repositories import ArticleRepository
from ...domain.upload_policy import UploadDecision, decide_upload
from ..ports import (
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

_SKIP_NOTES = {
    UploadSkipReason.ARTICLE_DATE_IN_FUTURE: "YouTubeアップロードはESA記事の日付が未来日のためスキップされました",
    UploadSkipReason.ALREADY_UPLOADED_TODAY: "YouTubeアップロードは当日分がすでに投稿済みのためスキップされました",
}


@dataclass(slots=True)
class GenerateDailyVideoInput:
    article_id: int | None = None
    force_upload: bool = False


@dataclass(slots=True)
class GenerateDailyVideoResult:
    status: PipelineStatus
    video: VideoAsset | None
    metadata: VideoMetadata | None
    youtube_video_id: str | None


class GenerateDailyVideo:
    """esa記事から動画を生成し、条件を満たせばYouTubeへ公開する。"""

    def __init__(
        self,
        article_repo: ArticleRepository,
        script_generator: ScriptGenerator,
        audio_synthesizer: AudioSynthesizer,
        subtitle_generator: SubtitleGenerator,
        metadata_generator: MetadataGenerator,
        thumbnail_generator: ThumbnailGenerator,
        video_composer: VideoComposer,
        publisher: VideoPublisher,
        logger: PipelineLogger,
        notifier: Notifier,
        metadata_store: MetadataStore,
        upload_history: UploadHistory,
        clock: Clock,
    ) -> None:
        self._article_repo = article_repo
        self._script_generator = script_generator
        self._audio_synthesizer = audio_synthesizer
        self._subtitle_generator = subtitle_generator
        self._metadata_generator = metadata_generator
        self._thumbnail_generator = thumbnail_generator
        self._video_composer = video_composer
        self._publisher = publisher
        self._logger = logger
        self._notifier = notifier
        self._metadata_store = metadata_store
        self._upload_history = upload_history
        self._clock = clock

    def execute(self, command: GenerateDailyVideoInput) -> GenerateDailyVideoResult:
        status = PipelineStatus(status=PipelineStage.STARTED, started_at=self._clock.now())
        self._logger.log({"event": "pipeline_started", "started_at": status.started_at.isoformat()})
        try:
            return self._run(command, status)
        except Exception as exc:  # pylint: disable=broad-except
            status.status = PipelineStage.FAILED
            status.completed_at = self._clock.now()
            status.notes.append(str(exc))
            self._logger.log({"event": "pipeline_failed", "error": str(exc)})
            self._notifier.notify(
                "AI-Daily動画の自動生成でエラーが発生しました",
                level="error",
                extra={"error": str(exc)},
            )
            raise

    def _run(self, command: GenerateDailyVideoInput, status: PipelineStatus) -> GenerateDailyVideoResult:
        today = status.started_at.date()

        article = self._resolve_article(command.article_id)
        status.status = PipelineStage.ARTICLE_READY
        self._logger.log({"event": "article_selected", "article_id": article.article_id})

        script = self._script_generator.build_script(article)
        status.status = PipelineStage.SCRIPT_READY
        self._logger.log({"event": "script_generated", "article_id": article.article_id})

        audio = self._audio_synthesizer.synthesize(script)
        status.status = PipelineStage.AUDIO_READY
        self._logger.log({"event": "audio_generated", "file_path": str(audio.file_path)})

        subtitles = self._subtitle_generator.generate_subtitles(script, audio)
        status.status = PipelineStage.SUBTITLES_READY
        self._logger.log({"event": "subtitles_generated", "file_path": str(subtitles.file_path)})

        metadata = self._metadata_generator.build_metadata(article, script)
        metadata.apply_daily_title(today)
        self._metadata_store.save(metadata)
        status.status = PipelineStage.METADATA_READY
        self._logger.log({"event": "metadata_generated", "title": metadata.title})

        self._attach_thumbnail(article, metadata, script, status)

        video = self._video_composer.compose(audio, subtitles)
        status.status = PipelineStage.VIDEO_READY
        self._logger.log({"event": "video_composed", "file_path": str(video.file_path)})

        decision = decide_upload(
            article=article,
            today=today,
            already_uploaded_today=self._upload_history.has_uploaded_on(today),
            force_upload=command.force_upload,
        )
        youtube_video_id = None
        if decision.allowed:
            youtube_video_id = self._publish(video, metadata, status, today)
        else:
            self._record_skip(article, metadata, decision, status)

        status.completed_at = self._clock.now()
        # 当日分が投稿済みで何もしなかった実行は、定期起動のたびに通知しない
        if decision.skip_reason is not UploadSkipReason.ALREADY_UPLOADED_TODAY:
            self._notify_completed(status, metadata, decision, youtube_video_id)
        return GenerateDailyVideoResult(
            status=status, video=video, metadata=metadata, youtube_video_id=youtube_video_id
        )

    def _resolve_article(self, article_id: int | None) -> Article:
        article = self._article_repo.by_id(article_id) if article_id else self._article_repo.latest()
        if not article:
            raise ArticleNotFoundError()
        return article

    def _attach_thumbnail(
        self, article: Article, metadata: VideoMetadata, script: Script, status: PipelineStatus
    ) -> None:
        """サムネイルは失敗しても動画生成を止めない。"""
        try:
            thumbnail_path = self._thumbnail_generator.generate(article, metadata, script)
            metadata.thumbnail_path = thumbnail_path.resolve()
            self._metadata_store.save(metadata)
            status.status = PipelineStage.THUMBNAIL_READY
            self._logger.log({"event": "thumbnail_generated", "file_path": str(thumbnail_path)})
        except Exception as exc:  # pragma: no cover - thumbnail is best-effort
            status.notes.append(f"thumbnail_failed: {exc}")
            self._logger.log({"event": "thumbnail_failed", "error": str(exc)})

    def _publish(
        self, video: VideoAsset, metadata: VideoMetadata, status: PipelineStatus, today: date
    ) -> str | None:
        youtube_video_id = self._publisher.publish(video, metadata)
        if not youtube_video_id:
            status.status = PipelineStage.VIDEO_SAVED
            return None

        status.status = PipelineStage.UPLOADED
        self._logger.log({"event": "video_uploaded", "youtube_id": youtube_video_id})
        self._upload_history.mark_uploaded(today)
        if metadata.thumbnail_path:
            self._logger.log(
                {
                    "event": "thumbnail_upload_requested",
                    "youtube_id": youtube_video_id,
                    "thumbnail_path": str(metadata.thumbnail_path),
                }
            )
        return youtube_video_id

    def _record_skip(
        self,
        article: Article,
        metadata: VideoMetadata,
        decision: UploadDecision,
        status: PipelineStatus,
    ) -> None:
        status.status = PipelineStage.VIDEO_SAVED
        payload: dict = {
            "event": "upload_skipped",
            "article_id": article.article_id,
            "article_published_at": article.published_at.isoformat() if article.published_at else None,
        }
        article_date = article.effective_date()
        if article_date:
            payload["article_date"] = article_date.isoformat()
        metadata_date = metadata.title_date()
        if metadata_date:
            payload["metadata_date"] = metadata_date.isoformat()
        payload["reason"] = decision.skip_reason or "unknown"
        self._logger.log(payload)

        note = _SKIP_NOTES.get(decision.skip_reason) if decision.skip_reason else None
        if note:
            status.notes.append(note)

    def _notify_completed(
        self,
        status: PipelineStatus,
        metadata: VideoMetadata,
        decision: UploadDecision,
        youtube_video_id: str | None,
    ) -> None:
        extra: dict = {"status": status.status}
        if youtube_video_id:
            extra["youtube_id"] = youtube_video_id
            extra["youtube_url"] = f"https://youtu.be/{youtube_video_id}"
            if metadata.title:
                extra["title"] = metadata.title
        elif decision.skip_reason:
            extra["reason"] = decision.skip_reason
        self._notifier.notify("AI-Daily動画の自動生成が完了しました", extra=extra)
