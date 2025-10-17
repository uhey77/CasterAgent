from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


class HedraClientError(RuntimeError):
    """Raised when the Hedra API returns an error response."""


class HedraTimeoutError(HedraClientError):
    """Raised when video generation does not finish within the allotted time."""


@dataclass(slots=True)
class HedraGenerationStatus:
    generation_id: str
    status: str
    download_url: str | None = None
    raw_payload: dict[str, Any] | None = None


class HedraClient:
    """Thin wrapper around the Hedra public API used to render avatar videos."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.hedra.com/web-app",
        assets_endpoint: str = "/public/assets",
        generation_endpoint: str = "/public/generations",
        status_endpoint: str = "/public/generations",
        poll_interval: float = 5.0,
        poll_timeout: float = 600.0,
    ) -> None:
        if not api_key:
            raise ValueError("Hedra API key is required.")

        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._assets_endpoint = assets_endpoint.rstrip("/")
        self._generation_endpoint = generation_endpoint.rstrip("/")
        self._status_endpoint = status_endpoint.rstrip("/")
        self._poll_interval = poll_interval
        self._poll_timeout = poll_timeout

    # --------------------------------------------------------------------- #
    # Asset helpers
    # --------------------------------------------------------------------- #
    def create_audio_asset(self, *, name: str) -> str:
        response = requests.post(
            f"{self._base_url}{self._assets_endpoint}",
            headers=self._json_headers(),
            json={"name": name, "type": "audio"},
            timeout=30,
        )
        self._raise_for_status(response)
        asset_id = response.json().get("id")
        if not asset_id:
            raise HedraClientError("Hedra API response did not include an asset id.")
        return str(asset_id)

    def upload_audio_asset(self, *, asset_id: str, audio_path: Path | None = None, audio_bytes: bytes | None = None) -> None:
        if audio_path is None and audio_bytes is None:
            raise ValueError("Either audio_path or audio_bytes must be provided.")
        if audio_bytes is None:
            audio_bytes = audio_path.read_bytes() if audio_path else b""
        files = {"file": ("audio.mp3", audio_bytes, "audio/mpeg")}
        response = requests.post(
            f"{self._base_url}{self._assets_endpoint}/{asset_id}/upload",
            headers=self._auth_headers(),
            files=files,
            timeout=120,
        )
        self._raise_for_status(response)

    # --------------------------------------------------------------------- #
    # Generation helpers
    # --------------------------------------------------------------------- #
    def create_video_generation(
        self,
        *,
        audio_asset_id: str,
        prompt: str,
        avatar_asset_id: str | None = None,
        duration_ms: int | None = None,
        resolution: str | None = None,
        aspect_ratio: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "type": "video",
            "audio_id": audio_asset_id,
            "generated_video_inputs": {
                "text_prompt": prompt,
            },
        }
        generated_inputs = payload["generated_video_inputs"]
        if duration_ms and duration_ms > 0:
            generated_inputs["duration_ms"] = duration_ms
        if resolution:
            generated_inputs["resolution"] = resolution
        if aspect_ratio:
            generated_inputs["aspect_ratio"] = aspect_ratio
        if avatar_asset_id:
            payload["start_keyframe_id"] = avatar_asset_id

        response = requests.post(
            f"{self._base_url}{self._generation_endpoint}",
            headers=self._json_headers(),
            json=payload,
            timeout=60,
        )
        self._raise_for_status(response)
        data = response.json()
        generation_id = data.get("id")
        if not generation_id:
            raise HedraClientError("Hedra API response did not include a generation id.")
        return str(generation_id)

    def wait_for_generation(self, generation_id: str) -> HedraGenerationStatus:
        deadline = time.monotonic() + self._poll_timeout
        while True:
            status = self.fetch_generation_status(generation_id)
            normalized = status.status.lower()
            if normalized in {"completed", "complete", "succeeded"} and status.download_url:
                return status
            if normalized in {"failed", "error"}:
                raise HedraClientError(f"Hedra reported failure for generation {generation_id}: {status.raw_payload}")
            if time.monotonic() >= deadline:
                raise HedraTimeoutError(f"Hedra generation {generation_id} timed out after {self._poll_timeout} seconds")
            time.sleep(self._poll_interval)

    def fetch_generation_status(self, generation_id: str) -> HedraGenerationStatus:
        response = requests.get(
            f"{self._base_url}{self._status_endpoint}/{generation_id}/status",
            headers=self._auth_headers(),
            timeout=30,
        )
        self._raise_for_status(response)
        payload = response.json()
        status = str(payload.get("status") or "unknown")
        download_url = payload.get("download_url") or payload.get("url")
        return HedraGenerationStatus(
            generation_id=generation_id,
            status=status,
            download_url=download_url,
            raw_payload=payload,
        )

    # --------------------------------------------------------------------- #
    # Download helpers
    # --------------------------------------------------------------------- #
    def download_asset(self, url: str, target_path: Path) -> None:
        response = requests.get(
            url,
            headers=self._auth_headers(),
            stream=True,
            timeout=120,
        )
        self._raise_for_status(response)
        with target_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    handle.write(chunk)

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #
    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "X-API-Key": self._api_key,
        }

    def _json_headers(self) -> dict[str, str]:
        headers = self._auth_headers()
        headers["Content-Type"] = "application/json"
        return headers

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            try:
                detail: Any = response.json()
            except Exception:  # pragma: no cover - defensive
                detail = response.text
            status = f"{response.status_code} {response.reason}"
            raise HedraClientError(f"Hedra API error ({status}): {detail}") from exc
