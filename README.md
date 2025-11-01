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
- (Optional) Hedra API key plus character IDs if you want photoreal conversational avatars instead of static slides
- (Optional) Sync Labs API key and a reference video for their lipsync service

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
- **Sync Labs API** for lipsync rendering when `SYNC_LABS_API_KEY` plus a template video are configured
- **Hedra API** for two-speaker avatar rendering when `HEDRA_API_KEY` is configured

## Notes

- Background artwork is generated automatically via `gpt-image-1` and cached per article.
- When Google credentials are absent, uploads are skipped gracefully. The composed video remains in `data/videos`.
- Ensure ImageMagick is installed if MoviePy requires it for text rendering on your platform.
- When Sync Labs credentials are provided the pipeline uploads the mixed audio track (and optional local video) to Sync Labs for lipsync rendering, waits for the output, then continues with topic overlays and delivery.
- When Hedra credentials are provided, the pipeline uploads the mixed audio track and per-line timing to Hedra, polls until the avatar video is ready, then downloads it before publishing. Without Sync Labs or Hedra configuration the legacy MoviePy-based slideshow renderer is used instead.

### Sync Labs configuration (optional)

```
SYNC_LABS_API_KEY=sk_sync_...
# Provide either a remote video URL or a local file path for the anchor footage
SYNC_LABS_VIDEO_URL=https://example.com/anchor.mp4
# SYNC_LABS_VIDEO_PATH=assets/anchor.mp4

# Optional tuning
SYNC_LABS_MODEL=lipsync-2
SYNC_LABS_SYNC_MODE=cut_off            # bounce | loop | cut_off | silence | remap
SYNC_LABS_ACTIVE_SPEAKER=false         # enable auto speaker detection
SYNC_LABS_TEMPERATURE=0.4              # expression intensity, 0.0-1.0
SYNC_LABS_OCCLUSION_DETECTION=false    # slows generation but handles hand-over-mouth cases
```

Additional polling or default values can be tweaked in `config/sync_labs.json`.

### Hedra configuration (optional)

```
HEDRA_API_KEY=sk_hedra_...
HEDRA_CHARACTER_A=chr_anchor_a        # Speaker A avatar
HEDRA_CHARACTER_B=chr_anchor_b        # Speaker B avatar
# Optional fine-tuning
HEDRA_SCENE_ID=scn_split_screen
HEDRA_VIDEO_WIDTH=1920
HEDRA_VIDEO_HEIGHT=1080
HEDRA_CONVERSATION_ENDPOINT=/videos
HEDRA_STATUS_ENDPOINT=/videos
HEDRA_POLL_INTERVAL_SECONDS=5
HEDRA_POLL_TIMEOUT_SECONDS=600
```

Consult Hedra's dashboard for available character/scene identifiers. If your tenant exposes different endpoints, override the `_ENDPOINT` variables accordingly.

## Testing

```
uv run pytest
```

Mocked responses are recommended for integration tests to avoid hitting external APIs during CI.

---
Happy automating!
