#!/usr/bin/env bash
set -eo pipefail

# .env の値を環境変数として読み込む
set -a
source .env
set +a

# ここから未定義変数を禁止
set -u

create_secret() {
  local key="$1"
  local value="$2"
  local lower
  lower=$(printf '%s' "$key" | tr '[:upper:]' '[:lower:]')
  local secret_name="ai-daily-${lower}"
  gcloud secrets create "$secret_name" --replication-policy=automatic 2>/dev/null || true
  printf '%s' "$value" | gcloud secrets versions add "$secret_name" --data-file=-
}

create_secret OPENAI_API_KEY "$OPENAI_API_KEY"
create_secret ESA_API_TOKEN "$ESA_API_TOKEN"
create_secret ESA_TEAM "$ESA_TEAM"
create_secret ESA_CATEGORY "$ESA_CATEGORY"
create_secret ESA_TAG "$ESA_TAG"
create_secret GOOGLE_PROJECT_ID "$GOOGLE_PROJECT_ID"
create_secret YOUTUBE_CHANNEL_ID "$YOUTUBE_CHANNEL_ID"
create_secret GOOGLE_CLIENT_ID "$GOOGLE_CLIENT_ID"
create_secret GOOGLE_CLIENT_SECRET "$GOOGLE_CLIENT_SECRET"
create_secret GOOGLE_REFRESH_TOKEN "$GOOGLE_REFRESH_TOKEN"
create_secret GOOGLE_DELEGATED_EMAIL "$GOOGLE_DELEGATED_EMAIL"
create_secret SYNC_LABS_API_KEY "$SYNC_LABS_API_KEY"
create_secret SYNC_LABS_SYNC_MODE "$SYNC_LABS_SYNC_MODE"
create_secret SLACK_WEBHOOK_URL "$SLACK_WEBHOOK_URL"

# Google の JSON 資格情報を Secret として保存
gcloud secrets create ai-daily-google-creds --replication-policy=automatic 2>/dev/null || true
gcloud secrets versions add ai-daily-google-creds \
  --data-file="$GOOGLE_APPLICATION_CREDENTIALS"
