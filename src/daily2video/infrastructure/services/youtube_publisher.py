from __future__ import annotations

import logging
import os
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
import json

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from ...core.settings import get_settings
from ...domain.interfaces import VideoPublisher
from ...domain.models import VideoAsset, VideoMetadata


class YouTubePublisher(VideoPublisher):  # pragma: no cover - network heavy
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
    
    def __init__(self) -> None:
        self._settings = get_settings()
        self._logger = logging.getLogger("ai_daily2video.youtube")
        self._credentials_path = Path("credentials/youtube_token.json")
        self._client_secrets_path = Path("credentials/youtube_client_secret.json")
        
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
        
        try:
            return self._perform_upload(video.file_path, body)
        except HttpError as exc:
            if self._is_signup_required(exc):
                self._logger.warning(
                    "Service account does not have YouTube upload permission; skipping upload."
                )
                return None
            self._logger.error("YouTube upload failed: %s", exc)
            raise RuntimeError(
                "YouTube upload failed. Ensure the configured credentials have upload permission."
            ) from exc
        except Exception as exc:
            self._logger.error("YouTube upload failed: %s", exc)
            raise

    def _perform_upload(self, file_path: Path, body: dict) -> str | None:
        media = MediaFileUpload(str(file_path), chunksize=-1, resumable=True)
        request = self._service.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None

        while response is None:
            status, response = request.next_chunk()
            if status:
                self._logger.info("Upload progress: %.2f%%", status.progress() * 100)

        youtube_id = response.get("id")
        self._logger.info("Video uploaded successfully: %s", youtube_id)
        return youtube_id

    def _is_signup_required(self, exc: HttpError) -> bool:
        try:
            data = json.loads(exc.content.decode("utf-8"))
        except Exception:
            return False

        errors = data.get("error", {}).get("errors")
        if not isinstance(errors, list):
            return False
        return any(item.get("reason") == "youtubeSignupRequired" for item in errors)

    def _build_service(self):
        if self._settings.google_application_credentials:
            return self._build_service_account_service()

        refresh_service = self._build_refresh_token_service()
        if refresh_service is not None:
            return refresh_service

        raise RuntimeError(
            "No valid authentication method found. Provide GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_REFRESH_TOKEN."
        )

    def _build_refresh_token_service(self):
        """環境変数に保存されたリフレッシュトークンを用いてサービスを構築"""
        settings = self._settings
        if not (settings.google_client_id and settings.google_client_secret and settings.google_refresh_token):
            return None

        creds = Credentials(
            token=None,
            refresh_token=settings.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=self.SCOPES,
        )

        try:
            creds.refresh(Request())
        except RefreshError as exc:
            self._logger.error("Failed to refresh YouTube credentials: %s", exc)
            return None

        return build("youtube", "v3", credentials=creds, cache_discovery=False)

    def _build_oauth2_service(self):
        """OAuth2認証でサービスを構築"""
        creds = None
        
        # トークンファイルが存在する場合は読み込み
        if self._credentials_path.exists():
            creds = Credentials.from_authorized_user_file(str(self._credentials_path), self.SCOPES)
        
        # 認証情報が無効または存在しない場合
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError:
                    self._logger.warning("Stored YouTube token invalid; removing and re-running consent flow.")
                    self._credentials_path.unlink(missing_ok=True)
                    creds = None
            if not creds or not creds.valid:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self._client_secrets_path), self.SCOPES
                )
                creds = flow.run_local_server(port=0, open_browser=True)
            
            # 認証情報を保存
            self._credentials_path.parent.mkdir(exist_ok=True)
            with open(self._credentials_path, 'w') as token:
                token.write(creds.to_json())
        
        return build("youtube", "v3", credentials=creds, cache_discovery=False)
    
    def _build_service_account_service(self):
        """サービスアカウント認証でサービスを構築（制限あり）"""
        credentials = ServiceAccountCredentials.from_service_account_file(
            self._settings.google_application_credentials,
            scopes=self.SCOPES,
        )
        self._logger.info("Using service account credentials for YouTube uploads.")
        return build("youtube", "v3", credentials=credentials, cache_discovery=False)
