from __future__ import annotations

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

    storage: StoragePaths = Field(default_factory=StoragePaths)
    output_root: Path = Field(default=Path("data"), alias="OUTPUT_ROOT")

    fastapi_reload: bool = Field(default=False)

    def prepare(self) -> None:
        if self.output_root:
            self.storage.root = Path(self.output_root)
        self.storage.ensure_directories()


@lru_cache
def get_settings() -> AppSettings:
    settings = AppSettings()
    settings.prepare()
    return settings
