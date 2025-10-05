from __future__ import annotations

import json
import logging
from typing import Iterable

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from ...core.settings import get_settings
from ...domain.interfaces import PipelineLogger


class ConsolePipelineLogger(PipelineLogger):
    def __init__(self) -> None:
        self._logger = logging.getLogger("ai_daily2video.pipeline")

    def log(self, payload: dict) -> None:
        self._logger.info(json.dumps(payload, ensure_ascii=False))

    def bulk_log(self, payloads: Iterable[dict]) -> None:
        for payload in payloads:
            self.log(payload)


class GoogleSheetsPipelineLogger(PipelineLogger):  # pragma: no cover - network heavy
    def __init__(self) -> None:
        self._settings = get_settings()
        if not self._settings.google_sheets_id:
            raise RuntimeError("Google Sheets ID is not configured")
        if not self._settings.google_drive_folder_id:
            logging.warning("Google Drive folder not configured; proceeding without it")
        self._service = self._build_service()

    def log(self, payload: dict) -> None:
        self.bulk_log([payload])

    def bulk_log(self, payloads: Iterable[dict]) -> None:
        values = [[json.dumps(item, ensure_ascii=False)] for item in payloads]
        body = {"values": values}
        self._service.spreadsheets().values().append(
            spreadsheetId=self._settings.google_sheets_id,
            range="logs!A:A",
            valueInputOption="RAW",
            body=body,
        ).execute()

    def _build_service(self):
        credentials = self._build_credentials()
        return build("sheets", "v4", credentials=credentials, cache_discovery=False)

    def _build_credentials(self):
        service_account_json = self._settings.google_application_credentials
        if not service_account_json:
            raise RuntimeError("Google service account JSON path is not configured")
        return Credentials.from_service_account_file(service_account_json, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ])


class CompositePipelineLogger(PipelineLogger):
    def __init__(self, *loggers: PipelineLogger) -> None:
        self._loggers = loggers

    def log(self, payload: dict) -> None:
        for logger in self._loggers:
            logger.log(payload)

    def bulk_log(self, payloads: Iterable[dict]) -> None:
        for logger in self._loggers:
            logger.bulk_log(payloads)


def build_pipeline_logger() -> PipelineLogger:
    settings = get_settings()
    loggers: list[PipelineLogger] = [ConsolePipelineLogger()]
    try:
        if settings.google_sheets_id:
            loggers.append(GoogleSheetsPipelineLogger())
    except Exception as exc:
        logging.warning("Google Sheets logger disabled: %s", exc)
    return CompositePipelineLogger(*loggers)
