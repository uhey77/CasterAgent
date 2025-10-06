from __future__ import annotations

import logging

from ...domain.interfaces import VideoPublisher
from ...domain.models import VideoAsset, VideoMetadata


class NoOpPublisher(VideoPublisher):
    def __init__(self) -> None:
        self._logger = logging.getLogger("ai_daily2video.publisher")

    def publish(self, video: VideoAsset, metadata: VideoMetadata) -> str | None:
        self._logger.info("Skipping upload for %s; returning local path", video.file_path)
        return None
