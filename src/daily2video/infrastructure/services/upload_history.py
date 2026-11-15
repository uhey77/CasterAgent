from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from ...application.ports import UploadHistory


class JsonUploadHistory(UploadHistory):
    """最後に投稿した日付を `last_upload.json` に記録する。"""

    def __init__(self, state_dir: Path) -> None:
        self._marker = state_dir / "last_upload.json"

    def has_uploaded_on(self, day: date) -> bool:
        if not self._marker.exists():
            return False
        try:
            payload = json.loads(self._marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        date_str = payload.get("date")
        if not date_str:
            return False
        try:
            return datetime.fromisoformat(date_str).date() == day
        except ValueError:
            return False

    def mark_uploaded(self, day: date) -> None:
        self._marker.parent.mkdir(parents=True, exist_ok=True)
        payload = {"date": day.isoformat()}
        self._marker.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
