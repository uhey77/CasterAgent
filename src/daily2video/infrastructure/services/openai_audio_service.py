from __future__ import annotations

import math
import tempfile
from pathlib import Path

from moviepy.editor import AudioFileClip, concatenate_audioclips
from openai import BadRequestError

from ...core.openai_client import get_openai_client
from ...core.settings import get_settings
from ...domain.interfaces import AudioSynthesizer
from ...domain.models import AudioAsset, DialogueSegment, Script


class OpenAIAudioService(AudioSynthesizer):
    def __init__(self) -> None:
        self._client = get_openai_client()
        self._settings = get_settings()

    def synthesize(self, script: Script) -> AudioAsset:
        target_path = self._settings.storage.audio_dir / f"{script.article_id}.mp3"

        min_speed = float(self._settings.tts_speed_min)
        max_speed = float(self._settings.tts_speed_max)
        if min_speed > max_speed:
            min_speed, max_speed = max_speed, min_speed

        target_min = max(0.0, float(self._settings.target_video_min_seconds))
        target_max = max(target_min, float(self._settings.target_video_max_seconds))
        max_attempts = max(1, int(self._settings.tts_resynthesis_max_attempts))

        speech_speed = float(self._settings.default_speech_speed)
        speech_speed = max(min_speed, min(max_speed, speech_speed))

        attempt = 0
        audio_segments: list[tuple[str, str, str]] = []
        clips: list[AudioFileClip] = []
        combined_audio = None
        total_duration = -1.0

        while True:
            attempt += 1
            audio_segments = self._synthesize_segments(script, speech_speed)
            if not audio_segments:
                raise ValueError("No script lines with text were available for audio synthesis.")

            clips = [AudioFileClip(segment_path) for segment_path, _, _ in audio_segments]
            combined_audio = concatenate_audioclips(clips)
            total_duration = combined_audio.duration if combined_audio.duration is not None else -1.0

            within_range = (
                total_duration > 0
                and target_min <= total_duration <= target_max
            )
            if within_range or attempt >= max_attempts:
                break

            if total_duration <= 0:
                break

            if total_duration > target_max:
                scale = total_duration / target_max
                adjusted_speed = min(max_speed, speech_speed * scale)
            else:
                scale = total_duration / target_min
                adjusted_speed = max(min_speed, speech_speed * scale)

            if math.isclose(adjusted_speed, speech_speed, rel_tol=1e-2):
                break

            # クリーンアップして再試行
            for clip in clips:
                clip.close()
            combined_audio.close()
            for segment_path, _, _ in audio_segments:
                Path(segment_path).unlink()

            speech_speed = adjusted_speed

        if combined_audio is None:
            raise RuntimeError("Audio synthesis failed to produce a combined clip.")

        combined_audio.write_audiofile(str(target_path))
        total_duration = combined_audio.duration if combined_audio.duration is not None else -1.0

        dialogue_segments: list[DialogueSegment] = []
        cursor = 0.0
        for clip, (_, speaker, text) in zip(clips, audio_segments):
            duration = clip.duration if clip.duration is not None else 0.0
            start = cursor
            end = cursor + duration
            dialogue_segments.append(
                DialogueSegment(speaker=speaker, text=text, start_seconds=start, end_seconds=end)
            )
            cursor = end

        for clip in clips:
            clip.close()
        combined_audio.close()
        for segment_path, _, _ in audio_segments:
            Path(segment_path).unlink()

        return AudioAsset(
            article_id=script.article_id,
            file_path=target_path,
            duration_seconds=total_duration,
            segments=dialogue_segments,
        )

    def _synthesize_segments(self, script: Script, speech_speed: float) -> list[tuple[str, str, str]]:
        audio_segments: list[tuple[str, str, str]] = []
        for line in script.lines:
            text = line.text.strip()
            if not text:
                continue

            speaker = (line.speaker or "").strip().upper()
            voice = "onyx" if speaker == "B" else "alloy"

            try:
                response = self._client.audio.speech.create(
                    model=self._settings.default_voice,
                    voice=voice,
                    input=text,
                    speed=speech_speed,
                    response_format="mp3",
                )
            except BadRequestError as exc:
                raise ValueError(f"OpenAI TTS synthesis failed: {exc}") from exc

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
                tmp_file.write(response.read())
                audio_segments.append((tmp_file.name, speaker or "A", text))

        return audio_segments
