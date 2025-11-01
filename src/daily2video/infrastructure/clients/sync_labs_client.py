from __future__ import annotations

import mimetypes
import time
from contextlib import ExitStack
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from requests import RequestException
from sync import Sync
from sync.common.types.generation import Generation
from sync.common.types.generation_options import GenerationOptions
from sync.common.types.video import Video as SyncVideo
from sync.core.api_error import ApiError
from sync.core.file import File as SyncFile


class SyncLabsClientError(RuntimeError):
    """Raised when the Sync Labs API reports an error."""


class SyncLabsTimeoutError(SyncLabsClientError):
    """Raised when a Sync Labs generation does not finish within the allotted time."""


@dataclass(slots=True)
class SyncLabsGenerationStatus:
    generation_id: str
    status: str
    download_url: str | None = None
    raw_payload: dict[str, Any] | None = None


@dataclass(slots=True)
class SyncVideoSource:
    """Represents the video asset that should be used for lipsync generation."""

    url: str | None = None
    file_path: Path | None = None

    def ensure_valid(self) -> None:
        if not self.url and not self.file_path:
            raise ValueError("Sync Labs video source requires either a URL or a local file path.")
        if self.file_path and not self.file_path.is_file():
            raise FileNotFoundError(f"Sync Labs video file not found: {self.file_path}")


class SyncLabsClient:
    """Thin wrapper around the official Sync Labs SDK that adds polling and download helpers."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.sync.so",
        poll_interval: float = 5.0,
        poll_timeout: float = 900.0,
    ) -> None:
        if not api_key:
            raise ValueError("Sync Labs API key is required.")

        self._client = Sync(api_key=api_key, base_url=base_url)
        self._poll_interval = poll_interval
        self._poll_timeout = poll_timeout

    def create_generation(
        self,
        *,
        model: str,
        video_source: SyncVideoSource,
        audio_path: Path,
        options: GenerationOptions | None = None,
        output_file_name: str | None = None,
    ) -> str:
        """
        Submits a lipsync job using a local audio file and either a remote or local video asset.
        """
        video_source.ensure_valid()
        if not audio_path.is_file():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        inputs: list[SyncVideo] = []
        if video_source.url:
            inputs.append(SyncVideo(url=video_source.url))

        request_options = None
        if output_file_name:
            request_options = {"additional_body_parameters": {"outputFileName": output_file_name}}

        try:
            with ExitStack() as stack:
                video_tuple: SyncFile | None = None
                if video_source.file_path:
                    video_file = stack.enter_context(video_source.file_path.open("rb"))
                    video_tuple = (
                        video_source.file_path.name,
                        video_file,
                        _guess_mime(video_source.file_path, default="video/mp4"),
                    )

                audio_file = stack.enter_context(audio_path.open("rb"))
                audio_tuple: SyncFile = (
                    audio_path.name,
                    audio_file,
                    _guess_mime(audio_path, default="audio/mpeg"),
                )

                encoded_inputs = json.dumps(
                    [_strip_none(video.model_dump()) for video in inputs], ensure_ascii=False
                ) if inputs else None
                encoded_options = (
                    json.dumps(_strip_none(options.model_dump()), ensure_ascii=False) if options else None
                )

                generation = self._client.generations.create_with_files(
                    model=model,
                    video=video_tuple,
                    audio=audio_tuple,
                    input=encoded_inputs,
                    options=encoded_options,
                    request_options=request_options,
                )
        except ApiError as exc:  # pragma: no cover - network errors
            raise SyncLabsClientError(getattr(exc, "body", str(exc))) from exc

        generation_id = str(generation.id or "").strip()
        if not generation_id:
            raise SyncLabsClientError("Sync Labs API did not return a generation id.")
        return generation_id

    def wait_for_generation(self, generation_id: str) -> SyncLabsGenerationStatus:
        """
        Polls the Sync Labs API until the requested generation completes or fails.
        """
        deadline = time.monotonic() + self._poll_timeout
        while True:
            try:
                generation = self._client.generations.get(generation_id)
            except ApiError as exc:  # pragma: no cover - network errors
                raise SyncLabsClientError(getattr(exc, "body", str(exc))) from exc

            status = str(generation.status)
            payload = _model_to_dict(generation)

            if status.upper() == "COMPLETED" and generation.output_url:
                return SyncLabsGenerationStatus(
                    generation_id=generation_id,
                    status=status,
                    download_url=generation.output_url,
                    raw_payload=payload,
                )

            if status.upper() in {"FAILED", "REJECTED"}:
                error_message = generation.error or "Sync Labs reported failure."
                raise SyncLabsClientError(f"Sync Labs generation {generation_id} failed: {error_message}")

            if time.monotonic() >= deadline:
                raise SyncLabsTimeoutError(
                    f"Sync Labs generation {generation_id} timed out after {self._poll_timeout} seconds"
                )

            time.sleep(self._poll_interval)

    def download_asset(self, url: str, target_path: Path) -> None:
        """
        Downloads the final rendered video to the provided path.
        """
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with requests.get(url, stream=True, timeout=120) as response:
                response.raise_for_status()
                with target_path.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            handle.write(chunk)
        except RequestException as exc:  # pragma: no cover - network errors
            raise SyncLabsClientError(f"Failed to download Sync Labs asset: {exc}") from exc


def _guess_mime(path: Path, *, default: str) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or default


def _model_to_dict(model: Generation) -> dict[str, Any]:
    if hasattr(model, "model_dump"):  # Pydantic v2
        return model.model_dump()
    if hasattr(model, "dict"):  # pragma: no cover - defensive
        return model.dict()  # type: ignore[attr-defined]
    return {}


def _strip_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
