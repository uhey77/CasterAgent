from __future__ import annotations

import math
import tempfile
from pathlib import Path

from google.api_core.exceptions import GoogleAPICallError, InvalidArgument
from google.cloud import texttospeech
from moviepy.editor import AudioFileClip, concatenate_audioclips

from ...core.settings import get_settings
from ...domain.interfaces import AudioSynthesizer
from ...domain.models import AudioAsset, DialogueSegment, Script


class GoogleTextToSpeechService(AudioSynthesizer):
    """Google Cloud Text-to-Speech を用いた音声合成サービス。"""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = texttospeech.TextToSpeechClient()

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

            within_range = total_duration > 0 and target_min <= total_duration <= target_max
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

        requested_voice = (self._settings.google_tts_voice_name or "").strip()
        primary_voice = requested_voice or "ja-JP-Neural2-C"
        default_candidates = [
            "ja-JP-Neural2-C",
            "ja-JP-Neural2-B",
            "ja-JP-Wavenet-C",
            "ja-JP-Standard-B",
        ]
        voice_candidates: list[str] = []
        for candidate in (primary_voice, *default_candidates):
            if candidate and candidate not in voice_candidates:
                voice_candidates.append(candidate)

        language_code = (self._settings.google_tts_language_code or "ja-JP").strip() or "ja-JP"
        gender = self._resolve_gender(self._settings.google_tts_ssml_gender)
        pitch = float(self._settings.google_tts_pitch)
        volume_gain_db = float(self._settings.google_tts_volume_gain_db)
        effects_profile = [
            profile.strip()
            for profile in (self._settings.google_tts_effects_profile_id or "").split(",")
            if profile.strip()
        ]

        for line in script.lines:
            text = line.text.strip()
            if not text:
                continue

            speaker_label = (line.speaker or "Narrator").strip() or "Narrator"

            response = None
            last_error: Exception | None = None
            for voice_name in voice_candidates:
                try:
                    synthesis_input = texttospeech.SynthesisInput(text=text)
                    voice_params = texttospeech.VoiceSelectionParams(
                        language_code=language_code,
                        name=voice_name,
                        ssml_gender=gender,
                    )
                    audio_config = texttospeech.AudioConfig(
                        audio_encoding=texttospeech.AudioEncoding.MP3,
                        speaking_rate=speech_speed,
                        pitch=pitch,
                        volume_gain_db=volume_gain_db,
                        effects_profile_id=effects_profile,
                    )
                    response = self._client.synthesize_speech(
                        input=synthesis_input,
                        voice=voice_params,
                        audio_config=audio_config,
                    )
                    break
                except (InvalidArgument, GoogleAPICallError) as exc:
                    last_error = exc
                    continue

            if response is None:
                raise ValueError(
                    f"Google TTS synthesis failed for all configured voices {voice_candidates}: {last_error}"
                ) from last_error

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
                tmp_file.write(response.audio_content)
                audio_segments.append((tmp_file.name, speaker_label, text))

        return audio_segments

    @staticmethod
    def _resolve_gender(value: str | None) -> texttospeech.SsmlVoiceGender:
        mapping = {
            "SSML_VOICE_GENDER_UNSPECIFIED": texttospeech.SsmlVoiceGender.SSML_VOICE_GENDER_UNSPECIFIED,
            "NEUTRAL": texttospeech.SsmlVoiceGender.NEUTRAL,
            "MALE": texttospeech.SsmlVoiceGender.MALE,
            "FEMALE": texttospeech.SsmlVoiceGender.FEMALE,
        }
        key = (value or "FEMALE").strip().upper()
        return mapping.get(key, texttospeech.SsmlVoiceGender.FEMALE)
