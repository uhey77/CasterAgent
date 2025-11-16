#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${GOOGLE_APPLICATION_CREDENTIALS_JSON:-}" ]]; then
  mkdir -p /tmp/google-creds
  printf '%s' "$GOOGLE_APPLICATION_CREDENTIALS_JSON" > /tmp/google-creds/key.json
  export GOOGLE_APPLICATION_CREDENTIALS=/tmp/google-creds/key.json
fi

exec uv run uvicorn daily2video.app:app --host 0.0.0.0 --port 8080
