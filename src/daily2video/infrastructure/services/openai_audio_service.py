from __future__ import annotations

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
        
        # 話者別に分割し、順序を保持
        audio_segments: list[tuple[str, str, str]] = []
        
        for line in script.lines:
            text = line.text.strip()
            if not text:
                continue

            speaker = (line.speaker or "").strip().upper()
            if speaker == "B":
                voice = "onyx"   # 男性っぽい深い声
            else:
                voice = "alloy"  # デフォルト（女性寄り）
            
            # 各セグメントを音声合成
            try:
                response = self._client.audio.speech.create(
                    model=self._settings.default_voice,
                    voice=voice,
                    input=text,
                    speed=self._settings.default_speech_speed,
                    response_format="mp3",
                )
                
                # 一時ファイルに保存
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
                    tmp_file.write(response.read())
                    audio_segments.append((tmp_file.name, speaker or "A", text))
                    
            except BadRequestError as exc:
                raise ValueError(f"OpenAI TTS synthesis failed: {exc}") from exc
        
        # 音声を結合
        if not audio_segments:
            raise ValueError("No script lines with text were available for audio synthesis.")

        clips = [AudioFileClip(segment_path) for segment_path, _, _ in audio_segments]
        combined_audio = concatenate_audioclips(clips)
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

        # クリーンアップ
        for clip in clips:
            clip.close()
        combined_audio.close()
        for segment_path, _, _ in audio_segments:
            Path(segment_path).unlink()  # 一時ファイル削除
        
        return AudioAsset(
            article_id=script.article_id,
            file_path=target_path,
            duration_seconds=total_duration,
            segments=dialogue_segments,
        )
