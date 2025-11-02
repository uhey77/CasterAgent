from __future__ import annotations

from pathlib import Path

from sync.common.types.active_speaker import ActiveSpeaker
from sync.common.types.generation_options import GenerationOptions

from ...core.settings import get_settings
from ...domain.interfaces import VideoComposer
from ...domain.models import AudioAsset, SubtitleFile, VideoAsset
from ..clients.sync_labs_client import (
    SyncLabsClient,
    SyncLabsClientError,
    SyncVideoSource,
)
from .topic_overlay import build_topic_overlay, overlay_topic_image


class SyncLabsVideoComposer(VideoComposer):
    """Video composer that uploads audio to Sync Labs for lipsync rendering."""

    def __init__(self, client: SyncLabsClient, video_source: SyncVideoSource) -> None:
        self._client = client
        self._video_source = video_source
        self._settings = get_settings()

    def compose(self, audio: AudioAsset, subtitles: SubtitleFile) -> VideoAsset:
        options = self._build_generation_options()
        generation_id = self._client.create_generation(
            model=self._settings.sync_labs_model,
            video_source=self._video_source,
            audio_path=audio.file_path,
            options=options,
            output_file_name=f"article-{audio.article_id}",
        )

        status = self._client.wait_for_generation(generation_id)
        if not status.download_url:
            raise SyncLabsClientError(f"Sync Labs generation {generation_id} completed without a download url.")

        target_path = self._target_path(audio.article_id)
        temp_render_path = target_path.with_suffix(".synclabs.mp4")
        self._client.download_asset(status.download_url, temp_render_path)

        duration = (
            audio.duration_seconds
            if audio.duration_seconds > 0
            else subtitles.segments[-1].end_seconds if subtitles.segments else 0.0
        )
        overlay_spec = build_topic_overlay(
            self._settings,
            audio.article_id,
            subtitles.segments,
            duration,
        )
        if overlay_spec:
            try:
                overlay_topic_image(temp_render_path, overlay_spec, target_path, duration)
                temp_render_path.unlink(missing_ok=True)
            except Exception as exc:  # pragma: no cover - best effort
                target_path.unlink(missing_ok=True)
                temp_render_path.rename(target_path)
                print(f"Sync Labs動画へのトピックオーバーレイ失敗: {exc}")
        else:
            target_path.unlink(missing_ok=True)
            temp_render_path.rename(target_path)

        return VideoAsset(article_id=audio.article_id, file_path=target_path, duration_seconds=duration)

    def _build_generation_options(self) -> GenerationOptions | None:
        sync_mode = (self._settings.sync_labs_sync_mode or "").strip()
        temperature = self._settings.sync_labs_temperature
        occlusion_detection = self._settings.sync_labs_occlusion_detection_enabled
        active_speaker = (
            ActiveSpeaker(auto_detect=True) if self._settings.sync_labs_active_speaker else None
        )

        if not any([sync_mode, temperature, occlusion_detection, active_speaker]):
            return None

        return GenerationOptions(
            sync_mode=sync_mode or None,
            temperature=temperature,
            occlusion_detection_enabled=occlusion_detection,
            active_speaker_detection=active_speaker,
        )

    def _target_path(self, article_id: int) -> Path:
        return self._settings.storage.videos_dir / f"{article_id}.mp4"
