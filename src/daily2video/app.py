from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import FastAPI

from .application.use_cases.generate_daily_video import GenerateDailyVideo
from .composition import build_generate_daily_video
from .core.settings import get_settings
from .presentation import api


@lru_cache
def _pipeline_use_case() -> GenerateDailyVideo:
    # 初回リクエスト時に一度だけ組み立て、プロセス内で再利用する
    return build_generate_daily_video(get_settings())


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
    app = FastAPI(title="AI Daily Video Pipeline", version="0.1.0")
    app.include_router(api.router)
    app.dependency_overrides[api.get_pipeline_use_case] = _pipeline_use_case

    @app.on_event("startup")
    async def startup_event() -> None:  # pragma: no cover - hook
        logging.info("FastAPI application started (reload=%s)", settings.fastapi_reload)

    return app


app = create_app()
