from __future__ import annotations

import logging

from fastapi import FastAPI

from .core.settings import get_settings
from .presentation import api


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
    app = FastAPI(title="AI Daily Video Pipeline", version="0.1.0")
    app.include_router(api.router)

    @app.on_event("startup")
    async def startup_event() -> None:  # pragma: no cover - hook
        logging.info("FastAPI application started (reload=%s)", settings.fastapi_reload)

    return app


app = create_app()
