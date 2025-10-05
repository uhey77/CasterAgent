from __future__ import annotations

import uvicorn

from ai_daily2video.app import app, create_app
from ai_daily2video.core.settings import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=8000,
        reload=settings.fastapi_reload,
    )


if __name__ == "__main__":
    main()
