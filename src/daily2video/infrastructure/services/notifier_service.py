from __future__ import annotations

import logging
from typing import Optional

import requests

from ...core.settings import get_settings
from ...domain.interfaces import Notifier


class SlackNotifier(Notifier):
    def __init__(self) -> None:
        self._settings = get_settings()
        self._logger = logging.getLogger("ai_daily2video.notifier")

    def notify(self, message: str, *, level: str = "info", extra: Optional[dict] = None) -> None:
        payload = {"text": message, "attachments": []}
        if extra:
            payload["attachments"].append({"text": "\n".join(f"{k}: {v}" for k, v in extra.items())})
        if not self._settings.slack_webhook_url:
            self._logger.log(getattr(logging, level.upper(), logging.INFO), payload)
            return
        response = requests.post(self._settings.slack_webhook_url, json=payload, timeout=10)
        if response.status_code >= 400:
            self._logger.error("Slack notification failed: %s", response.text)
