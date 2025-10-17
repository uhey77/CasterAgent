from __future__ import annotations

import json
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

    def ensure_directories(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for child in (
            self.scripts_dir,
            self.audio_dir,
            self.subtitles_dir,
            self.images_dir,
            self.videos_dir,
            self.metadata_dir,
        ):
            child.mkdir(parents=True, exist_ok=True)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


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

    slack_webhook_url: str = Field(default="")

    default_voice: str = Field(default="gpt-4o-mini-tts")
    default_speech_speed: float = Field(default=1.05)
    default_font_path: Path | None = Field(default=None)

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

    storage: StoragePaths = Field(default_factory=StoragePaths)
    output_root: Path = Field(default=Path("data"), alias="OUTPUT_ROOT")

    fastapi_reload: bool = Field(default=False)

    def prepare(self) -> None:
        if self.output_root:
            self.storage.root = Path(self.output_root)
        self.storage.ensure_directories()
        self._load_hedra_config()

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



@lru_cache
def get_settings() -> AppSettings:
    settings = AppSettings()
    settings.prepare()
    return settings
