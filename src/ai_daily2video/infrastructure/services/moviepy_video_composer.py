from __future__ import annotations

from typing import List

from moviepy.editor import AudioFileClip, CompositeVideoClip, ImageClip, TextClip

from ...core.settings import get_settings
from ...domain.interfaces import VideoComposer
from ...domain.models import AudioAsset, GeneratedImage, SubtitleFile, SubtitleSegment, VideoAsset


class MoviePyVideoComposer(VideoComposer):
    def __init__(self) -> None:
        self._settings = get_settings()

    def compose(
        self,
        audio: AudioAsset,
        subtitles: SubtitleFile,
        background: GeneratedImage,
    ) -> VideoAsset:
        output_path = self._settings.storage.videos_dir / f"{audio.article_id}.mp4"

        audio_clip = AudioFileClip(str(audio.file_path))
        duration = audio_clip.duration
        image_clip = (
            ImageClip(str(background.file_path))
            .set_duration(duration)
            .resize(height=1080)
            .set_position("center")
        )
        subtitle_clips = self._build_subtitle_clips(subtitles.segments, duration)
        video_clip = CompositeVideoClip([image_clip] + subtitle_clips)
        final_clip = video_clip.set_audio(audio_clip)

        final_clip.write_videofile(
            str(output_path),
            codec="libx264",
            audio_codec="aac",
            fps=30,
            bitrate="4000k",
            threads=4,
            temp_audiofile=str(output_path.with_suffix(".temp.m4a")),
            remove_temp=True,
        )

        audio_clip.close()
        image_clip.close()
        final_clip.close()
        for clip in subtitle_clips:
            clip.close()

        return VideoAsset(article_id=audio.article_id, file_path=output_path, duration_seconds=duration)

    def _build_subtitle_clips(self, segments: List[SubtitleSegment], duration: float):
        font_path = str(self._settings.default_font_path) if self._settings.default_font_path else "Arial"
        clips = []
        for segment in segments:
            start = max(segment.start_seconds, 0.0)
            end = min(segment.end_seconds, duration)
            if start >= end:
                continue
            text = segment.text.replace("\n", " ")
            clip = (
                TextClip(
                    text,
                    fontsize=60,
                    font=font_path,
                    color="white",
                    method="caption",
                    size=(1600, None),
                )
                .on_color(size=(1920, 160), color=(0, 0, 0), col_opacity=0.55)
                .set_position(("center", 820))
                .set_start(start)
                .set_end(end)
            )
            clips.append(clip)
        return clips
