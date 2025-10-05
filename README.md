# AI Daily 2 Video

AI Daily 2 Video is a clean-architecture FastAPI service that converts esa "AI-Daily" posts into narrated videos ready for YouTube. The automation flow fetches the latest article, drafts a conversational script, generates voice, subtitles, a background illustration, composes the video, and optionally uploads it to YouTube. All AI capabilities rely solely on the OpenAI API family (chat, TTS, transcription, image generation).

## Project Layout

```
src/ai_daily2video/
├── app.py                 # FastAPI bootstrap
├── core/                  # Configuration & OpenAI client factories
├── domain/                # Entities and abstract contracts (DDD)
├── application/           # Use cases orchestrating the workflow
├── infrastructure/        # External service implementations (OpenAI, ESA, Google APIs, MoviePy)
└── presentation/          # FastAPI routers and dependency wiring
```

## Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- OpenAI API key with access to GPT-4o, Whisper, and image generation endpoints
- ESA API token and team information
- (Optional) Google Cloud service account for Sheets logging and YouTube uploads
- (Optional) Slack Incoming Webhook for notifications

## Getting Started

```bash
# Install dependencies with uv
uv sync

# Configure environment
cp .env.example .env
# Edit .env with OpenAI/ESA/Google credentials

# Run API server
uv run python main.py
# or
uv run uvicorn ai_daily2video.app:app --reload
```

The API exposes:
- `GET /health` – readiness probe
- `POST /pipeline/run` – triggers the end-to-end generation. Provide `{ "article_id": 123 }` to process a specific esa post or omit to use the latest.

Artifacts (scripts, audio, subtitles, backgrounds, videos, metadata) are stored under `data/` by default.

## Tooling

- **FastAPI** for HTTP interface
- **Ruff** for linting (`uv run ruff check src tests`)
- **Pytest** for automated tests (`uv run pytest`)
- **MoviePy** for video composition

## Notes

- Background artwork is generated automatically via `gpt-image-1` and cached per article.
- When Google credentials are absent, uploads are skipped gracefully. The composed video remains in `data/videos`.
- Ensure ImageMagick is installed if MoviePy requires it for text rendering on your platform.

## Testing

```
uv run pytest
```

Mocked responses are recommended for integration tests to avoid hitting external APIs during CI.

---
Happy automating!
