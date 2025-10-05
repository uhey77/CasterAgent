from __future__ import annotations

import tempfile
from pathlib import Path

from moviepy.editor import AudioFileClip, concatenate_audioclips
from openai import BadRequestError

from ...core.openai_client import get_openai_client
from ...core.settings import get_settings
from ...domain.interfaces import AudioSynthesizer
from ...domain.models import AudioAsset, Script


class OpenAIAudioService(AudioSynthesizer):
    def __init__(self) -> None:
        self._client = get_openai_client()
        self._settings = get_settings()

    def synthesize(self, script: Script) -> AudioAsset:
        target_path = self._settings.storage.audio_dir / f"{script.article_id}.mp3"
        
        # 話者別に分割し、順序を保持
        audio_segments = []
        
        for line in script.lines:
            if not line.text.strip():
                continue
                
            if line.text.startswith("A: "):
                text = line.text[3:]  # "A: " を除去
                voice = "alloy"
            elif line.text.startswith("B: "):
                text = line.text[3:]  # "B: " を除去
                voice = "echo"
            else:
                text = line.text
                voice = "alloy"  # デフォルト
            
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
                    audio_segments.append(tmp_file.name)
                    
            except BadRequestError as exc:
                raise ValueError(f"OpenAI TTS synthesis failed: {exc}") from exc
        
        # 音声を結合
        if audio_segments:
            clips = [AudioFileClip(segment) for segment in audio_segments]
            combined_audio = concatenate_audioclips(clips)
            combined_audio.write_audiofile(str(target_path))
            
            # クリーンアップ
            for clip in clips:
                clip.close()
            for segment in audio_segments:
                Path(segment).unlink()  # 一時ファイル削除
        
        return AudioAsset(article_id=script.article_id, file_path=target_path, duration_seconds=-1.0)
