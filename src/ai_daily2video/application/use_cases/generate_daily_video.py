from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ...domain.interfaces import (
    ArticleRepository,
    AudioSynthesizer,
    BackgroundImageGenerator,
    MetadataGenerator,
    Notifier,
    PipelineLogger,
    ScriptGenerator,
    SubtitleGenerator,
    VideoComposer,
    VideoPublisher,
)
from ...domain.models import (
    PipelineError,
    PipelineStatus,
    VideoAsset,
    VideoMetadata,
)


@dataclass(slots=True)
class GenerateDailyVideoInput:
    article_id: Optional[int] = None


@dataclass(slots=True)
class GenerateDailyVideoResult:
    status: PipelineStatus
    video: Optional[VideoAsset]
    metadata: Optional[VideoMetadata]
    youtube_video_id: Optional[str]


class GenerateDailyVideo:
    def __init__(
        self,
        article_repo: ArticleRepository,
        script_generator: ScriptGenerator,
        audio_synthesizer: AudioSynthesizer,
        subtitle_generator: SubtitleGenerator,
        background_generator: BackgroundImageGenerator,
        metadata_generator: MetadataGenerator,
        video_composer: VideoComposer,
        publisher: VideoPublisher,
        logger: PipelineLogger,
        notifier: Notifier,
    ) -> None:
        self._article_repo = article_repo
        self._script_generator = script_generator
        self._audio_synthesizer = audio_synthesizer
        self._subtitle_generator = subtitle_generator
        self._background_generator = background_generator
        self._metadata_generator = metadata_generator
        self._video_composer = video_composer
        self._publisher = publisher
        self._logger = logger
        self._notifier = notifier

    def execute(self, command: GenerateDailyVideoInput) -> GenerateDailyVideoResult:
        status = PipelineStatus(status="started", started_at=datetime.utcnow())
        self._logger.log({"event": "pipeline_started", "started_at": status.started_at.isoformat()})
        try:
            article = self._resolve_article(command.article_id)
            status.status = "article_ready"
            self._logger.log({"event": "article_selected", "article_id": article.article_id})

            script = self._script_generator.build_script(article)
            status.status = "script_ready"
            self._logger.log({"event": "script_generated", "article_id": article.article_id})

            audio = self._audio_synthesizer.synthesize(script)
            status.status = "audio_ready"
            self._logger.log({"event": "audio_generated", "file_path": str(audio.file_path)})

            subtitles = self._subtitle_generator.generate_subtitles(script, audio)
            status.status = "subtitles_ready"
            self._logger.log({"event": "subtitles_generated", "file_path": str(subtitles.file_path)})

            background = self._background_generator.create_image(article)
            status.status = "background_ready"
            self._logger.log({"event": "background_generated", "file_path": str(background.file_path)})

            metadata = self._metadata_generator.build_metadata(article, script)
            status.status = "metadata_ready"
            self._logger.log({"event": "metadata_generated", "title": metadata.title})

            video = self._video_composer.compose(audio, subtitles, background)
            status.status = "video_ready"
            self._logger.log({"event": "video_composed", "file_path": str(video.file_path)})

            youtube_video_id = self._publisher.publish(video, metadata)
            if youtube_video_id:
                status.status = "uploaded"
                self._logger.log({"event": "video_uploaded", "youtube_id": youtube_video_id})
            else:
                status.status = "video_saved"

            status.completed_at = datetime.utcnow()
            self._notifier.notify("AI-Daily動画の自動生成が完了しました", extra={"status": status.status})
            return GenerateDailyVideoResult(status=status, video=video, metadata=metadata, youtube_video_id=youtube_video_id)
        except Exception as exc:  # pylint: disable=broad-except
            status.status = "failed"
            status.completed_at = datetime.utcnow()
            status.notes.append(str(exc))
            self._logger.log({"event": "pipeline_failed", "error": str(exc)})
            self._notifier.notify(
                "AI-Daily動画の自動生成でエラーが発生しました",
                level="error",
                extra={"error": str(exc)},
            )
            raise

    def _resolve_article(self, article_id: int | None):
        article = self._article_repo.by_id(article_id) if article_id else self._article_repo.latest()
        if not article:
            raise PipelineError("article", "対象の記事が見つかりませんでした")
        return article
