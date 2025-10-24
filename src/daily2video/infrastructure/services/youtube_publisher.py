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
        service_account_service = self._build_service_account_service()
        if service_account_service is not None:
            return service_account_service

        refresh_service = self._build_refresh_token_service()
        if refresh_service is not None:
            return refresh_service

        oauth_service = self._build_oauth2_service()
        if oauth_service is not None:
            return oauth_service

        raise RuntimeError(
            "YouTube upload requires OAuth認証情報が必要です。google_client_id/google_client_secretと有効なリフレッシュトークン、"
            "またはcredentials/youtube_client_secret.jsonを用意してください。"
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
        if not self._client_secrets_path.is_file() and not (
            self._settings.google_client_id and self._settings.google_client_secret
        ):
            self._logger.info("No OAuth client secrets found for YouTube upload.")
            return None

        creds = None
        if self._credentials_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self._credentials_path), self.SCOPES)
            except Exception:
                self._logger.warning("Stored YouTube token could not be parsed; re-running consent flow.")
                self._credentials_path.unlink(missing_ok=True)
                creds = None

        if creds and creds.valid:
            return build("youtube", "v3", credentials=creds, cache_discovery=False)

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                if creds.valid:
                    return build("youtube", "v3", credentials=creds, cache_discovery=False)
            except RefreshError:
                self._logger.warning("Stored YouTube token invalid; removing and re-running consent flow.")
                self._credentials_path.unlink(missing_ok=True)
                creds = None

        flow = self._build_oauth_flow()
        if flow is None:
            return None

        creds = flow.run_local_server(port=0, open_browser=True, access_type="offline", prompt="consent")
        self._credentials_path.parent.mkdir(exist_ok=True)
        self._credentials_path.write_text(creds.to_json(), encoding="utf-8")
        return build("youtube", "v3", credentials=creds, cache_discovery=False)

    def _build_oauth_flow(self):
        if self._client_secrets_path.is_file():
            return InstalledAppFlow.from_client_secrets_file(str(self._client_secrets_path), self.SCOPES)

        if self._settings.google_client_id and self._settings.google_client_secret:
            client_config = {
                "installed": {
                    "client_id": self._settings.google_client_id,
                    "client_secret": self._settings.google_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
            return InstalledAppFlow.from_client_config(client_config, self.SCOPES)

        return None

    def _build_service_account_service(self):
        credentials_path = (self._settings.google_application_credentials or "").strip()
        delegated_email = (self._settings.google_delegated_email or "").strip()
        if not credentials_path:
            return None

        if not delegated_email:
            self._logger.warning(
                "サービスアカウントでYouTubeにアップロードするにはGOOGLE_DELEGATED_EMAIL（委任ユーザーのメールアドレス）が必要です。"
            )
            return None

        try:
            credentials = ServiceAccountCredentials.from_service_account_file(
                credentials_path,
                scopes=self.SCOPES,
            ).with_subject(delegated_email)
        except FileNotFoundError:
            self._logger.error("Service account credentials file not found at %s", credentials_path)
            return None
        except Exception as exc:
            self._logger.error("Failed to load service account credentials: %s", exc)
            return None

        self._logger.info(
            "Using service account with delegated user %s for YouTube uploads.", delegated_email
        )
        try:
            return build("youtube", "v3", credentials=credentials, cache_discovery=False)
        except HttpError as exc:
            if self._is_signup_required(exc):
                self._logger.warning(
                    "DelegatedアカウントにYouTubeアップロード権限がありません。コンソールからアクセス権を付与してください。"
                )
                return None
            raise
