from __future__ import annotations

from pathlib import Path
import json

from daily2video.core.settings import get_settings
from daily2video.domain.models import AudioAsset, DialogueSegment, SubtitleFile, SubtitleSegment
from daily2video.infrastructure.clients.sync_labs_client import (
    SyncLabsGenerationStatus,
    SyncVideoSource,
)
from daily2video.infrastructure.services import sync_labs_video_composer
from daily2video.infrastructure.services.sync_labs_video_composer import SyncLabsVideoComposer


class StubSyncLabsClient:
    def __init__(self) -> None:
        self.submissions: list[dict] = []
        self.downloaded: list[tuple[str, Path]] = []

    def create_generation(self, *, model, video_source, audio_path, options, output_file_name) -> str:
        self.submissions.append(
            {
                "model": model,
                "video_source": video_source,
                "audio_path": audio_path,
                "options": options,
                "output_file_name": output_file_name,
            }
        )
        return "sync-gen-1"

    def wait_for_generation(self, generation_id: str) -> SyncLabsGenerationStatus:
        return SyncLabsGenerationStatus(
            generation_id=generation_id,
            status="COMPLETED",
            download_url="https://example.com/out.mp4",
            raw_payload={"status": "COMPLETED"},
        )

    def download_asset(self, url: str, target_path: Path) -> None:
        self.downloaded.append((url, target_path))
        target_path.write_bytes(b"video")


def test_sync_labs_video_composer(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("SYNC_LABS_SYNC_MODE", "cut_off")
    monkeypatch.setenv("SYNC_LABS_API_KEY", "dummy-key")
    monkeypatch.setattr(sync_labs_video_composer, "build_topic_overlay", lambda *args, **kwargs: None)

    get_settings.cache_clear()
    try:
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"\x00\x00")
        audio_asset = AudioAsset(
            article_id=42,
            file_path=audio_path,
            duration_seconds=12.0,
            segments=[
                DialogueSegment(speaker="Narrator", text="hello", start_seconds=0.0, end_seconds=6.0),
                DialogueSegment(speaker="Narrator", text="world", start_seconds=6.0, end_seconds=12.0),
            ],
        )
        subtitles = SubtitleFile(
            article_id=42,
            file_path=tmp_path / "subs.srt",
            segments=[
                SubtitleSegment(0.0, 6.0, "hello"),
                SubtitleSegment(6.0, 12.0, "world"),
            ],
        )
        client = StubSyncLabsClient()
        video_source = SyncVideoSource(url="https://example.com/template.mp4")
        composer = SyncLabsVideoComposer(client, video_source)

        video_asset = composer.compose(audio_asset, subtitles)

        assert client.submissions, "client should receive a submission"
        submission = client.submissions[0]
        assert submission["model"] == get_settings().sync_labs_model
        encoded_options = submission["options"]
        if isinstance(encoded_options, str):
            options_payload = json.loads(encoded_options)
            assert options_payload.get("sync_mode") == "cut_off"
        else:
            assert encoded_options.sync_mode == "cut_off"
        assert client.downloaded[0][0] == "https://example.com/out.mp4"
        assert video_asset.file_path.exists()
    finally:
        get_settings.cache_clear()
