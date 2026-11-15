"""Composition Root: 設定を読み、具体実装を選んでユースケースへ接続する。"""

from __future__ import annotations

import logging

from openai import OpenAI

from .application.ports import PipelineLogger, VideoComposer, VideoPublisher
from .application.use_cases.generate_daily_video import GenerateDailyVideo
from .core.settings import AppSettings, get_settings
from .infrastructure.clients.esa_client import EsaRestClient
from .infrastructure.clients.hedra_client import HedraClient
from .infrastructure.clients.sync_labs_client import SyncLabsClient, SyncVideoSource
from .infrastructure.services.google_tts_service import GoogleTextToSpeechService
from .infrastructure.services.hedra_video_composer import HedraVideoComposer
from .infrastructure.services.logging_service import build_pipeline_logger
from .infrastructure.services.metadata_store import JsonMetadataStore
from .infrastructure.services.moviepy_video_composer import MoviePyVideoComposer
from .infrastructure.services.noop_publisher import NoOpPublisher
from .infrastructure.services.notifier_service import SlackNotifier
from .infrastructure.services.openai_script_service import OpenAIScriptService
from .infrastructure.services.openai_subtitle_service import OpenAISubtitleService
from .infrastructure.services.sync_labs_video_composer import SyncLabsVideoComposer
from .infrastructure.services.system_clock import SystemClock
from .infrastructure.services.thumbnail_service import ThumbnailGeneratorService
from .infrastructure.services.upload_history import JsonUploadHistory
from .infrastructure.services.youtube_publisher import YouTubePublisher


def build_generate_daily_video(settings: AppSettings | None = None) -> GenerateDailyVideo:
    settings = settings or get_settings()
    logger = build_pipeline_logger(settings)
    openai_client = _build_openai_client(settings)
    script_service = OpenAIScriptService(openai_client, settings)  # 台本とメタデータを兼ねる

    return GenerateDailyVideo(
        article_repo=EsaRestClient(settings),
        script_generator=script_service,
        audio_synthesizer=GoogleTextToSpeechService(settings),
        subtitle_generator=OpenAISubtitleService(openai_client, settings),
        metadata_generator=script_service,
        video_composer=_build_video_composer(settings, logger),
        thumbnail_generator=ThumbnailGeneratorService(settings),
        publisher=_build_publisher(settings, logger),
        logger=logger,
        notifier=SlackNotifier(settings),
        metadata_store=JsonMetadataStore(),
        upload_history=JsonUploadHistory(settings.storage.state_dir),
        clock=SystemClock(),
    )


def _build_openai_client(settings: AppSettings) -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return OpenAI(api_key=settings.openai_api_key)


def _build_publisher(settings: AppSettings, logger: PipelineLogger) -> VideoPublisher:
    try:
        if settings.google_application_credentials:
            return YouTubePublisher(settings)
    except Exception as exc:
        logging.warning("Falling back to NoOpPublisher: %s", exc)
        logger.log({"event": "youtube_publisher_unavailable", "error": str(exc)})
    return NoOpPublisher()


def _build_video_composer(settings: AppSettings, logger: PipelineLogger) -> VideoComposer:
    """Sync Labs → Hedra → ローカルffmpeg の順に、利用可能なものを選ぶ。"""
    if settings.sync_labs_api_key:
        try:
            video_source = _build_sync_video_source(settings)
            sync_client = SyncLabsClient(
                api_key=settings.sync_labs_api_key,
                base_url=settings.sync_labs_base_url,
                poll_interval=settings.sync_labs_poll_interval_seconds,
                poll_timeout=settings.sync_labs_poll_timeout_seconds,
            )
            return SyncLabsVideoComposer(sync_client, video_source, settings)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logging.warning("Falling back because Sync Labs is unavailable: %s", exc)
            logger.log({"event": "sync_labs_unavailable", "error": str(exc)})

    if settings.hedra_api_key:
        try:
            hedra_client = HedraClient(
                api_key=settings.hedra_api_key,
                base_url=settings.hedra_base_url,
                assets_endpoint=settings.hedra_assets_endpoint,
                generation_endpoint=settings.hedra_generation_endpoint,
                status_endpoint=settings.hedra_status_endpoint,
                poll_interval=settings.hedra_poll_interval_seconds,
                poll_timeout=settings.hedra_poll_timeout_seconds,
            )
            return HedraVideoComposer(hedra_client, settings)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logging.warning("Falling back to MoviePy composer because Hedra is unavailable: %s", exc)
            logger.log({"event": "hedra_unavailable", "error": str(exc)})
    return MoviePyVideoComposer(settings)


def _build_sync_video_source(settings: AppSettings) -> SyncVideoSource:
    url = (settings.sync_labs_video_url or "").strip() or None
    source = SyncVideoSource(url=url, file_path=settings.sync_labs_video_path)
    source.ensure_valid()
    return source
