from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StoragePaths(BaseModel):
    root: Path = Field(default=Path("data"))

    @property
    def scripts_dir(self) -> Path:
        return self.root / "scripts"

    @property
    def audio_dir(self) -> Path:
        return self.root / "audio"

    @property
    def subtitles_dir(self) -> Path:
        return self.root / "subtitles"

    @property
    def images_dir(self) -> Path:
        return self.root / "images"

    @property
    def videos_dir(self) -> Path:
        return self.root / "videos"

    @property
    def metadata_dir(self) -> Path:
        return self.root / "metadata"

    @property
    def articles_dir(self) -> Path:
        return self.root / "articles"

    def ensure_directories(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for child in (
            self.scripts_dir,
            self.audio_dir,
            self.subtitles_dir,
            self.images_dir,
            self.videos_dir,
            self.metadata_dir,
            self.articles_dir,
        ):
            child.mkdir(parents=True, exist_ok=True)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


def _load_env_file(path: Path) -> None:
    if not path or not path.exists():
        return
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError:
        return

    for raw_line in contents.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file(ENV_FILE)


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    esa_api_token: str = Field(default="")
    esa_team: str = Field(default="")
    esa_category: str = Field(default="")
    esa_tag: str = Field(default="")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    google_application_credentials: str = Field(default="", alias="GOOGLE_APPLICATION_CREDENTIALS")
    google_project_id: str = Field(default="")
    google_sheets_id: str = Field(default="")
    google_drive_folder_id: str = Field(default="")
    youtube_channel_id: str = Field(default="")
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")
    google_refresh_token: str = Field(default="", alias="GOOGLE_REFRESH_TOKEN")
    google_delegated_email: str = Field(default="", alias="GOOGLE_DELEGATED_EMAIL")

    slack_webhook_url: str = Field(default="")

    google_tts_language_code: str = Field(default="ja-JP", alias="GOOGLE_TTS_LANGUAGE_CODE")
    google_tts_voice_name: str = Field(default="ja-JP-Neural2-C", alias="GOOGLE_TTS_VOICE_NAME")
    google_tts_ssml_gender: str = Field(default="FEMALE", alias="GOOGLE_TTS_GENDER")
    google_tts_pitch: float = Field(default=3.0, alias="GOOGLE_TTS_PITCH")
    google_tts_volume_gain_db: float = Field(default=0.0, alias="GOOGLE_TTS_GAIN_DB")
    google_tts_effects_profile_id: str = Field(default="", alias="GOOGLE_TTS_EFFECTS_PROFILE")
    default_speech_speed: float = Field(default=1.05)
    default_font_path: Path | None = Field(default=None)
    tts_speed_min: float = Field(default=0.85)
    tts_speed_max: float = Field(default=1.8)
    tts_resynthesis_max_attempts: int = Field(default=4)
    target_video_min_seconds: float = Field(default=255.0)
    target_video_max_seconds: float = Field(default=285.0)

    scheduler_cron: str = Field(default="0 22 * * *")

    hedra_api_key: str = Field(default="", alias="HEDRA_API_KEY")
    hedra_base_url: str = Field(default="https://api.hedra.com/web-app", alias="HEDRA_BASE_URL")
    hedra_avatar_id: str = Field(default="", alias="HEDRA_AVATAR_ID")
    hedra_character_id: str = Field(default="", alias="CHARACTER_ID")
    hedra_character_a: str = Field(default="", alias="HEDRA_CHARACTER_A")
    hedra_character_b: str = Field(default="", alias="HEDRA_CHARACTER_B")
    hedra_scene_id: str = Field(default="", alias="HEDRA_SCENE_ID")
    hedra_video_width: int = Field(default=1920, alias="HEDRA_VIDEO_WIDTH")
    hedra_video_height: int = Field(default=1080, alias="HEDRA_VIDEO_HEIGHT")
    hedra_poll_interval_seconds: float = Field(default=5.0, alias="HEDRA_POLL_INTERVAL_SECONDS")
    hedra_poll_timeout_seconds: float = Field(default=600.0, alias="HEDRA_POLL_TIMEOUT_SECONDS")
    hedra_assets_endpoint: str = Field(default="/public/assets", alias="HEDRA_ASSETS_ENDPOINT")
    hedra_generation_endpoint: str = Field(default="/public/generations", alias="HEDRA_GENERATION_ENDPOINT")
    hedra_status_endpoint: str = Field(default="/public/generations", alias="HEDRA_STATUS_ENDPOINT")
    hedra_config_path: Path = Field(default=Path("config/hedra.json"), alias="HEDRA_CONFIG_PATH")

    sync_labs_api_key: str = Field(default="", alias="SYNC_LABS_API_KEY")
    sync_labs_base_url: str = Field(default="https://api.sync.so", alias="SYNC_LABS_BASE_URL")
    sync_labs_model: str = Field(default="lipsync-2", alias="SYNC_LABS_MODEL")
    sync_labs_video_url: str = Field(default="", alias="SYNC_LABS_VIDEO_URL")
    sync_labs_video_path: Path | None = Field(default=None, alias="SYNC_LABS_VIDEO_PATH")
    sync_labs_sync_mode: str = Field(default="cut_off", alias="SYNC_LABS_SYNC_MODE")
    sync_labs_active_speaker: bool = Field(default=False, alias="SYNC_LABS_ACTIVE_SPEAKER")
    sync_labs_poll_interval_seconds: float = Field(default=5.0, alias="SYNC_LABS_POLL_INTERVAL_SECONDS")
    sync_labs_poll_timeout_seconds: float = Field(default=900.0, alias="SYNC_LABS_POLL_TIMEOUT_SECONDS")
    sync_labs_temperature: float | None = Field(default=None, alias="SYNC_LABS_TEMPERATURE")
    sync_labs_occlusion_detection_enabled: bool = Field(
        default=False, alias="SYNC_LABS_OCCLUSION_DETECTION"
    )
    sync_labs_config_path: Path = Field(default=Path("config/sync_labs.json"), alias="SYNC_LABS_CONFIG_PATH")

    storage: StoragePaths = Field(default_factory=StoragePaths)
    output_root: Path = Field(default=Path("data"), alias="OUTPUT_ROOT")

    fastapi_reload: bool = Field(default=False)

    def prepare(self) -> None:
        if self.output_root:
            self.storage.root = Path(self.output_root)
        self.storage.ensure_directories()
        self._load_hedra_config()
        self._load_sync_labs_config()

    def _load_hedra_config(self) -> None:
        if not self.hedra_config_path:
            return
        config_path = Path(self.hedra_config_path)
        if not config_path.is_file():
            return
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raise ValueError(f"Could not parse Hedra config JSON at {config_path}")

        poll_timeout = data.get("poll_timeout_seconds")
        if poll_timeout is not None:
            try:
                self.hedra_poll_timeout_seconds = float(poll_timeout)
            except (TypeError, ValueError) as exc:
                raise ValueError("hedra.poll_timeout_seconds must be a number") from exc

        poll_interval = data.get("poll_interval_seconds")
        if poll_interval is not None:
            try:
                self.hedra_poll_interval_seconds = float(poll_interval)
            except (TypeError, ValueError) as exc:
                raise ValueError("hedra.poll_interval_seconds must be a number") from exc

    def _load_sync_labs_config(self) -> None:
        if not self.sync_labs_config_path:
            return
        config_path = Path(self.sync_labs_config_path)
        if not config_path.is_file():
            return
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:  # pragma: no cover - invalid configuration
            raise ValueError(f"Could not parse Sync Labs config JSON at {config_path}") from exc

        poll_timeout = data.get("poll_timeout_seconds")
        if poll_timeout is not None:
            try:
                self.sync_labs_poll_timeout_seconds = float(poll_timeout)
            except (TypeError, ValueError) as exc:
                raise ValueError("sync_labs.poll_timeout_seconds must be a number") from exc

        poll_interval = data.get("poll_interval_seconds")
        if poll_interval is not None:
            try:
                self.sync_labs_poll_interval_seconds = float(poll_interval)
            except (TypeError, ValueError) as exc:
                raise ValueError("sync_labs.poll_interval_seconds must be a number") from exc

        model = data.get("model")
        if model:
            self.sync_labs_model = str(model)

        sync_mode = data.get("sync_mode")
        if sync_mode:
            self.sync_labs_sync_mode = str(sync_mode)



@lru_cache
def get_settings() -> AppSettings:
    settings = AppSettings()
    settings.prepare()
    return settings
