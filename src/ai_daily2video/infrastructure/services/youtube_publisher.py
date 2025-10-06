from __future__ import annotations

import logging
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
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
            
        except Exception as e:
            self._logger.error("YouTube upload failed: %s", str(e))
            raise

    def _build_service(self):
        # 1. OAuth2認証を優先して試行
        if self._client_secrets_path.exists():
            return self._build_oauth2_service()
            
        # 2. フォールバック: サービスアカウント認証
        if self._settings.google_application_credentials:
            self._logger.warning("Using service account for YouTube API (may have limitations)")
            return self._build_service_account_service()
            
        raise RuntimeError(
            "No valid authentication method found. "
            "Please provide either OAuth2 client secrets or service account credentials."
        )

    def _build_oauth2_service(self):
        """OAuth2認証でサービスを構築"""
        creds = None
        
        # トークンファイルが存在する場合は読み込み
        if self._credentials_path.exists():
            creds = Credentials.from_authorized_user_file(str(self._credentials_path), self.SCOPES)
        
        # 認証情報が無効または存在しない場合
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                # トークンをリフレッシュ
                creds.refresh(Request())
            else:
                # 初回認証フロー
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
        return build("youtube", "v3", credentials=credentials, cache_discovery=False)
