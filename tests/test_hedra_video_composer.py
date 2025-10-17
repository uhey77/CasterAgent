from __future__ import annotations

from pathlib import Path

from daily2video.core.settings import get_settings
from daily2video.domain.models import (
    AudioAsset,
    DialogueSegment,
    GeneratedImage,
    SubtitleFile,
    SubtitleSegment,
)
from daily2video.infrastructure.clients.hedra_client import HedraGenerationStatus
from daily2video.infrastructure.services.hedra_video_composer import HedraVideoComposer


class StubHedraClient:
    def __init__(self) -> None:
        self.created_assets: list[str] = []
        self.uploaded_assets: list[tuple[str, Path | None, bytes | None]] = []
        self.generations: list[dict] = []
        self.downloaded_to: Path | None = None

    def create_audio_asset(self, *, name: str) -> str:
        self.created_assets.append(name)
        return "asset-1"

    def upload_audio_asset(self, *, asset_id: str, audio_path: Path | None = None, audio_bytes: bytes | None = None) -> None:
        self.uploaded_assets.append((asset_id, audio_path, audio_bytes))

    def create_video_generation(self, *, audio_asset_id: str, prompt: str, avatar_asset_id: str | None = None, duration_ms: int | None = None, resolution: str | None = None, aspect_ratio: str | None = None) -> str:
        self.generations.append(
            {
                "audio_asset_id": audio_asset_id,
                "prompt": prompt,
                "avatar_asset_id": avatar_asset_id,
                "duration_ms": duration_ms,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
            }
        )
        return "gen-1"

    def wait_for_generation(self, generation_id: str) -> HedraGenerationStatus:
        return HedraGenerationStatus(
            generation_id=generation_id,
            status="completed",
            download_url="https://example.com/video.mp4",
        )

    def download_asset(self, url: str, target_path: Path) -> None:
        self.downloaded_to = target_path
        target_path.write_bytes(b"fake-video")


def test_hedra_video_composer_builds_timeline(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("HEDRA_AVATAR_ID", "chr_avatar_primary")

    get_settings.cache_clear()  # ensure environment overrides are picked up
    try:
        client = StubHedraClient()
        composer = HedraVideoComposer(client)

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"\x00\x00")
        audio_asset = AudioAsset(
            article_id=100,
            file_path=audio_path,
            duration_seconds=10.0,
            segments=[
                DialogueSegment(speaker="A", text="こんにちは", start_seconds=0.0, end_seconds=4.0),
                DialogueSegment(speaker="B", text="こんばんは", start_seconds=4.0, end_seconds=8.0),
            ],
        )
        subtitles = SubtitleFile(
            article_id=100,
            file_path=tmp_path / "subtitles.srt",
            segments=[
                SubtitleSegment(0.0, 4.0, "こんにちは"),
                SubtitleSegment(4.0, 8.0, "こんばんは"),
            ],
        )
        background = GeneratedImage(article_id=100, file_path=tmp_path / "bg.png")

        video_asset = composer.compose(audio_asset, subtitles, background)

        assert client.created_assets == ["article-100"]
        assert client.uploaded_assets[0][0] == "asset-1"
        assert client.uploaded_assets[0][1] == audio_path
        assert client.generations[0]["audio_asset_id"] == "asset-1"
        assert client.generations[0]["avatar_asset_id"] == "chr_avatar_primary"
        assert "こんにちは こんばんは" in client.generations[0]["prompt"]
        assert client.downloaded_to == video_asset.file_path
        assert video_asset.file_path.exists()
    finally:
        get_settings.cache_clear()
