import math
import struct
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from daily2video.domain.models import AudioAsset, SubtitleFile, SubtitleSegment
from daily2video.infrastructure.services.ffmpeg_tools import (
    audio_duration,
    concatenate_audio,
    ffmpeg,
)
from daily2video.infrastructure.services.moviepy_video_composer import MoviePyVideoComposer


def make_audio(path: Path, duration: float) -> None:
    rate = 16000
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(
            b"".join(
                struct.pack("<h", int(5000 * math.sin(2 * math.pi * 440 * i / rate)))
                for i in range(int(rate * duration))
            )
        )


def test_audio_concatenation(tmp_path):
    first, second, output = tmp_path / "a.wav", tmp_path / "b.wav", tmp_path / "out.mp3"
    make_audio(first, 0.4)
    make_audio(second, 0.5)
    concatenate_audio([str(first), str(second)], output)
    assert abs(audio_duration(output) - 0.9) < 0.15


def test_video_with_timed_subtitle(tmp_path, monkeypatch):
    audio = tmp_path / "sound.wav"
    make_audio(audio, 1.0)
    composer = MoviePyVideoComposer.__new__(MoviePyVideoComposer)
    composer._settings = SimpleNamespace(storage=SimpleNamespace(videos_dir=tmp_path))
    monkeypatch.setattr(
        "daily2video.infrastructure.services.moviepy_video_composer.build_topic_overlay",
        lambda *args: None,
    )
    result = composer.compose(
        AudioAsset(article_id=1, file_path=audio, duration_seconds=1.0),
        SubtitleFile(
            article_id=1,
            file_path=tmp_path / "s.srt",
            segments=[SubtitleSegment(0.2, 0.8, "字幕テスト")],
        ),
    )
    assert result.file_path.is_file()
    assert abs(audio_duration(result.file_path) - 1.0) < 0.2
    frame = tmp_path / "frame.png"
    subprocess.run(
        [
            ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            "0.5",
            "-i",
            str(result.file_path),
            "-frames:v",
            "1",
            str(frame),
        ],
        check=True,
    )
    with Image.open(frame) as image:
        assert image.size == (1920, 1080)
        pixels = image.convert("RGB").crop((100, 880, 1820, 1080))
        assert max(channel for pixel in pixels.get_flattened_data() for channel in pixel) > 180


def test_tts_combines_segments_and_preserves_timing(tmp_path, monkeypatch):
    from daily2video.domain.models import Script, ScriptLine
    from daily2video.infrastructure.services.google_tts_service import GoogleTextToSpeechService

    service = GoogleTextToSpeechService.__new__(GoogleTextToSpeechService)
    service._settings = SimpleNamespace(
        storage=SimpleNamespace(audio_dir=tmp_path),
        tts_speed_min=0.5,
        tts_speed_max=2.0,
        target_video_min_seconds=0.0,
        target_video_max_seconds=10.0,
        tts_resynthesis_max_attempts=1,
        default_speech_speed=1.0,
    )
    first, second = tmp_path / "one.wav", tmp_path / "two.wav"
    make_audio(first, 0.4)
    make_audio(second, 0.5)
    monkeypatch.setattr(
        service,
        "_synthesize_segments",
        lambda *args: [(str(first), "A", "first"), (str(second), "B", "second")],
    )
    result = service.synthesize(
        Script(article_id=2, raw_text="first", lines=[ScriptLine(speaker="A", text="first")])
    )
    assert result.file_path.is_file()
    assert abs(result.duration_seconds - 0.9) < 0.1
    assert len(result.segments) == 2
    assert abs(result.segments[1].start_seconds - 0.4) < 0.05
    assert not first.exists() and not second.exists()
