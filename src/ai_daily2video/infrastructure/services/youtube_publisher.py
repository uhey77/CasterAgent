from __future__ import annotations

import logging
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from ...core.settings import get_settings
from ...domain.interfaces import VideoPublisher
from ...domain.models import VideoAsset, VideoMetadata


class YouTubePublisher(VideoPublisher):  # pragma: no cover - network heavy
    def __init__(self) -> None:
        self._settings = get_settings()
        self._logger = logging.getLogger("ai_daily2video.youtube")
        if not self._settings.google_application_credentials:
            raise RuntimeError("Google application credentials are not configured")
        self._service = self._build_service()

    def publish(self, video: VideoAsset, metadata: VideoMetadata) -> str | None:
        body = {
            "snippet": {
                "title": metadata.title,
                "description": metadata.description,
                "tags": metadata.tags,
                "categoryId": metadata.category_id,
                "defaultLanguage": metadata.language,
            },
            "status": {
                "privacyStatus": metadata.privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }
        media = MediaFileUpload(str(video.file_path), chunksize=-1, resumable=True)
        request = self._service.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                self._logger.info("Upload progress: %.2f%%", status.progress() * 100)
        youtube_id = response.get("id")
        self._logger.info("Video uploaded successfully: %s", youtube_id)
        return youtube_id

    def _build_service(self):
        credentials = Credentials.from_service_account_file(
            self._settings.google_application_credentials,
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
        )
        return build("youtube", "v3", credentials=credentials, cache_discovery=False)
