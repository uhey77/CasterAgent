from __future__ import annotations

from pathlib import Path
from typing import List

from ...core.settings import get_settings
from ...domain.interfaces import VideoComposer
from ...domain.models import AudioAsset, DialogueSegment, GeneratedImage, SubtitleFile, VideoAsset
from ..clients.hedra_client import HedraClient, HedraClientError


class HedraVideoComposer(VideoComposer):
    """Video composer that offloads avatar rendering to the Hedra API."""

    def __init__(self, client: HedraClient) -> None:
        self._client = client
        self._settings = get_settings()

    def compose(self, audio: AudioAsset, subtitles: SubtitleFile, background: GeneratedImage) -> VideoAsset:
        avatar_id = self._primary_avatar_id()
        if not avatar_id:
            raise HedraClientError(
                "No Hedra avatar asset configured. Please set HEDRA_AVATAR_ID to an image asset ID from Hedra Studio."
            )

        asset_name = f"article-{audio.article_id}"
        audio_asset_id = self._client.create_audio_asset(name=asset_name)
        self._client.upload_audio_asset(asset_id=audio_asset_id, audio_path=audio.file_path)

        prompt = self._build_prompt(audio.segments)
        duration_ms = self._estimate_duration_ms(audio, subtitles)

        generation_id = self._client.create_video_generation(
            audio_asset_id=audio_asset_id,
            avatar_asset_id=avatar_id,
            prompt=prompt,
            duration_ms=duration_ms,
        )
        status = self._client.wait_for_generation(generation_id)
        if not status.download_url:
            raise HedraClientError(f"Hedra generation {generation_id} completed but no download URL was returned.")

        target_path = self._target_path(audio.article_id)
        self._client.download_asset(status.download_url, target_path)

        duration = audio.duration_seconds if audio.duration_seconds > 0 else subtitles.segments[-1].end_seconds if subtitles.segments else 0.0
        return VideoAsset(article_id=audio.article_id, file_path=target_path, duration_seconds=duration)

    def _target_path(self, article_id: int) -> Path:
        return self._settings.storage.videos_dir / f"{article_id}.mp4"

    def _primary_avatar_id(self) -> str | None:
        avatar_id = (getattr(self._settings, "hedra_avatar_id", "") or "").strip()
        return avatar_id or None

    def _build_prompt(self, segments: List[DialogueSegment]) -> str:
        texts = [segment.text.strip() for segment in segments if segment.text.strip()]
        if not texts:
            return "AIニュースのモノローグ音声トラック。"
        prompt = " ".join(texts)
        # Hedra API expects a reasonably short prompt; trim to avoid payload bloat.
        return prompt[:500]

    def _estimate_duration_ms(self, audio: AudioAsset, subtitles: SubtitleFile) -> int | None:
        if audio.duration_seconds and audio.duration_seconds > 0:
            return int(audio.duration_seconds * 1000)
        if subtitles.segments:
            return int(subtitles.segments[-1].end_seconds * 1000)
        return None
