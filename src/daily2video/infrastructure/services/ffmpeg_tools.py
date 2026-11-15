from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg


def ffmpeg() -> str:
    system_binary = shutil.which("ffmpeg")
    if system_binary:
        return system_binary
    homebrew_binary = Path("/opt/homebrew/opt/ffmpeg/bin/ffmpeg")
    if homebrew_binary.is_file():
        return str(homebrew_binary)
    return imageio_ffmpeg.get_ffmpeg_exe()


def audio_duration(path: str | Path) -> float:
    result = subprocess.run(
        [ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if not match:
        raise ValueError(f"Could not determine audio duration: {path}")
    hours, minutes, seconds = match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if duration <= 0:
        raise ValueError(f"Audio duration must be positive: {path}")
    return duration


def concatenate_audio(paths: list[str], output: Path) -> None:
    if not paths:
        raise ValueError("At least one audio file is required")
    command = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"]
    for path in paths:
        command.extend(["-i", path])
    inputs = "".join(f"[{index}:a]" for index in range(len(paths)))
    command.extend(
        [
            "-filter_complex",
            f"{inputs}concat=n={len(paths)}:v=0:a=1[out]",
            "-map",
            "[out]",
            "-c:a",
            "libmp3lame",
            str(output),
        ]
    )
    subprocess.run(command, check=True, capture_output=True, text=True)
