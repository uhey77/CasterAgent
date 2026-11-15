from __future__ import annotations

from datetime import datetime

from ...application.ports import Clock
from ...domain.models import JST


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(JST)
