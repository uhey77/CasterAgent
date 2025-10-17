from __future__ import annotations

import logging

from ...core.settings import get_settings
from ...domain.interfaces import Notifier, PipelineLogger, VideoComposer, VideoPublisher
from ...infrastructure.clients.esa_client import EsaRestClient
from ...infrastructure.clients.hedra_client import HedraClient
from ...infrastructure.services.hedra_video_composer import HedraVideoComposer
from ...infrastructure.services.logging_service import build_pipeline_logger
from ...infrastructure.services.moviepy_video_composer import MoviePyVideoComposer
from ...infrastructure.services.noop_publisher import NoOpPublisher
from ...infrastructure.services.notifier_service import SlackNotifier
from ...infrastructure.services.openai_audio_service import OpenAIAudioService
from ...infrastructure.services.openai_image_service import OpenAIImageService
from ...infrastructure.services.openai_script_service import OpenAIScriptService
from ...infrastructure.services.openai_subtitle_service import OpenAISubtitleService
from ...infrastructure.services.youtube_publisher import YouTubePublisher
from ..use_cases.generate_daily_video import GenerateDailyVideo


def build_pipeline_use_case() -> GenerateDailyVideo:
    settings = get_settings()
    logger = _build_logger()
    article_repo = EsaRestClient()
    script_generator = OpenAIScriptService()
    audio = OpenAIAudioService()
    subtitles = OpenAISubtitleService()
    background = OpenAIImageService()
    metadata = script_generator  # shares the same service
    video = _build_video_composer(settings, logger)
    notifier = _build_notifier()
    publisher = _build_publisher(settings, logger)

    return GenerateDailyVideo(
        article_repo=article_repo,
        script_generator=script_generator,
        audio_synthesizer=audio,
        subtitle_generator=subtitles,
        background_generator=background,
        metadata_generator=metadata,
        video_composer=video,
        publisher=publisher,
        logger=logger,
        notifier=notifier,
    )


def _build_logger() -> PipelineLogger:
    return build_pipeline_logger()


def _build_notifier() -> Notifier:
    return SlackNotifier()


def _build_publisher(settings, logger: PipelineLogger) -> VideoPublisher:
    try:
        if settings.google_application_credentials:
            return YouTubePublisher()
    except Exception as exc:
        logging.warning("Falling back to NoOpPublisher: %s", exc)
        logger.log({"event": "youtube_publisher_unavailable", "error": str(exc)})
    return NoOpPublisher()


def _build_video_composer(settings, logger: PipelineLogger) -> VideoComposer:
    if settings.hedra_api_key:
        try:
            client = HedraClient(
                api_key=settings.hedra_api_key,
                base_url=settings.hedra_base_url,
                assets_endpoint=settings.hedra_assets_endpoint,
                generation_endpoint=settings.hedra_generation_endpoint,
                status_endpoint=settings.hedra_status_endpoint,
                poll_interval=settings.hedra_poll_interval_seconds,
                poll_timeout=settings.hedra_poll_timeout_seconds,
            )
            return HedraVideoComposer(client)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logging.warning("Falling back to MoviePy composer because Hedra is unavailable: %s", exc)
            logger.log({"event": "hedra_unavailable", "error": str(exc)})
    return MoviePyVideoComposer()
