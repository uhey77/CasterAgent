from __future__ import annotations

from functools import lru_cache

from ..application.services.pipeline_service import build_pipeline_use_case
from ..application.use_cases.generate_daily_video import GenerateDailyVideo


@lru_cache
def get_pipeline_use_case() -> GenerateDailyVideo:
    return build_pipeline_use_case()
