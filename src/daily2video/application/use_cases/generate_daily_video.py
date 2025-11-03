from __future__ import annotations

import json
import re
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta, date
from typing import Optional

from ...domain.interfaces import (
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
from ...domain.models import (
    Article,
    PipelineError,
    PipelineStatus,
    VideoAsset,
    VideoMetadata,
)
from ...core.settings import StoragePaths

JST = timezone(timedelta(hours=9))


def _now_jst() -> datetime:
    return datetime.now(timezone.utc).astimezone(JST)


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
        metadata_generator: MetadataGenerator,
        video_composer: VideoComposer,
        publisher: VideoPublisher,
        logger: PipelineLogger,
        notifier: Notifier,
        storage: StoragePaths,
    ) -> None:
        self._article_repo = article_repo
        self._script_generator = script_generator
        self._audio_synthesizer = audio_synthesizer
        self._subtitle_generator = subtitle_generator
        self._metadata_generator = metadata_generator
        self._video_composer = video_composer
        self._publisher = publisher
        self._logger = logger
        self._notifier = notifier
        self._storage = storage

    def execute(self, command: GenerateDailyVideoInput) -> GenerateDailyVideoResult:
        status = PipelineStatus(status="started", started_at=_now_jst())
        self._logger.log({"event": "pipeline_started", "started_at": status.started_at.isoformat()})
        try:
            send_notification = True
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

            metadata = self._metadata_generator.build_metadata(article, script)
            self._ensure_metadata_title_date(metadata)
            status.status = "metadata_ready"
            self._logger.log({"event": "metadata_generated", "title": metadata.title})

            video = self._video_composer.compose(audio, subtitles)
            status.status = "video_ready"
            self._logger.log({"event": "video_composed", "file_path": str(video.file_path)})

            should_upload, skip_reason = self._should_upload_video(article, metadata)
            youtube_video_id = None

            if should_upload:
                youtube_video_id = self._publisher.publish(video, metadata)
                if youtube_video_id:
                    status.status = "uploaded"
                    self._logger.log({"event": "video_uploaded", "youtube_id": youtube_video_id})
                    self._mark_uploaded_today()
                else:
                    status.status = "video_saved"
            else:
                status.status = "video_saved"
                skip_payload = {
                    "event": "upload_skipped",
                    "article_id": article.article_id,
                    "article_published_at": (
                        article.published_at.isoformat() if article.published_at else None
                    ),
                }
                metadata_date = self._extract_metadata_date(metadata)
                if metadata_date:
                    skip_payload["metadata_date"] = metadata_date.isoformat()
                skip_payload["reason"] = skip_reason or "unknown"
                self._logger.log(skip_payload)
                if skip_reason == "article_date_in_future":
                    status.notes.append("YouTubeアップロードはESA記事の日付が未来日のためスキップされました")
                elif skip_reason == "already_uploaded_today":
                    status.notes.append("YouTubeアップロードは当日分がすでに投稿済みのためスキップされました")
                    send_notification = False

            status.completed_at = _now_jst()
            if send_notification:
                notification_extra = {"status": status.status}
                if youtube_video_id:
                    notification_extra["youtube_id"] = youtube_video_id
                    notification_extra["youtube_url"] = f"https://youtu.be/{youtube_video_id}"
                    if metadata and metadata.title:
                        notification_extra["title"] = metadata.title
                elif not should_upload and skip_reason:
                    notification_extra["reason"] = skip_reason
                self._notifier.notify(
                    "AI-Daily動画の自動生成が完了しました",
                    extra=notification_extra,
                )
            return GenerateDailyVideoResult(status=status, video=video, metadata=metadata, youtube_video_id=youtube_video_id)
        except Exception as exc:  # pylint: disable=broad-except
            status.status = "failed"
            status.completed_at = _now_jst()
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

    def _should_upload_video(self, article: Article, metadata: VideoMetadata | None) -> tuple[bool, Optional[str]]:
        """メタデータのタイトル日付か記事日付に基づいてアップロード可否を判断"""
        current_date = _now_jst().date()

        if self._has_uploaded_today():
            return False, "already_uploaded_today"

        metadata_date = self._extract_metadata_date(metadata)
        if metadata_date and metadata_date == current_date:
            return True, None

        if not article:
            return False, "article_missing"
        if not article.published_at:
            return True, None

        if article.published_at.tzinfo:
            published_date = article.published_at.astimezone(JST).date()
        else:
            published_date = article.published_at.date()

        if published_date <= current_date:
            return True, None
        return False, "article_date_in_future"

    def _ensure_metadata_title_date(self, metadata: VideoMetadata | None) -> None:
        if not metadata:
            return
        today_str = _now_jst().strftime("%Y-%m-%d")
        metadata.title = f"AI Daily—{today_str}"

        if metadata.file_path:
            payload = {
                "title": metadata.title,
                "description": metadata.description,
                "tags": metadata.tags,
                "category_id": metadata.category_id,
                "privacy_status": metadata.privacy_status,
                "language": metadata.language,
            }
            metadata.file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _extract_metadata_date(metadata: VideoMetadata | None) -> date | None:
        if not metadata or not metadata.title:
            return None
        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", metadata.title)
        if not match:
            return None
        try:
            year, month, day = map(int, match.groups())
            return date(year, month, day)
        except ValueError:
            return None

    def _upload_marker_path(self) -> Path:
        return self._storage.state_dir / "last_upload.json"

    def _has_uploaded_today(self) -> bool:
        marker = self._upload_marker_path()
        if not marker.exists():
            return False
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        date_str = payload.get("date")
        if not date_str:
            return False
        try:
            last_date = datetime.fromisoformat(date_str).date()
        except ValueError:
            return False
        return last_date == _now_jst().date()

    def _mark_uploaded_today(self) -> None:
        marker = self._upload_marker_path()
        marker.parent.mkdir(parents=True, exist_ok=True)
        payload = {"date": _now_jst().date().isoformat()}
        marker.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
