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
        
        # 16:9アスペクト比（1920x1080）に強制変更
        image_clip = (
            ImageClip(str(background.file_path))
            .set_duration(duration)
            .resize((1920, 1080))  # 横長サイズに強制変更
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
        clips = []
        
        # 日本語対応フォントのフルパスを直接指定
        font_candidates = [
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc", 
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/ee89e7987a76cc8cfdff36c96bd7bc77655b343e.asset/AssetData/YuGothic-Medium.otf",
            None
        ]
        
        selected_font = None
        for font in font_candidates:
            try:
                test_clip = TextClip("テスト日本語", fontsize=20, font=font, color="white")
                test_clip.close()
                selected_font = font
                print(f"使用フォント: {font}")
                break
            except Exception as e:
                print(f"フォント '{font}' は使用できません: {e}")
                continue
        
        if selected_font is None:
            print("ERROR: 利用可能な日本語フォントが見つかりません")
            return []
        
        for segment in segments:
            start = max(segment.start_seconds, 0.0)
            end = min(segment.end_seconds, duration)
            if start >= end:
                continue
            text = segment.text.replace("\n", " ")
            print(f"字幕作成中: {text[:30]}...")
            
            try:
                clip = (
                    TextClip(
                        text,
                        fontsize=60,
                        font=selected_font,
                        color="white",
                        method="caption",
                        size=(1600, None),  # 横幅を1600に設定（1920より少し小さく）
                    )
                    .on_color(
                        size=(1920, 200),  # 背景は1920幅に合わせる
                        color=(0, 0, 0),
                        col_opacity=0.8
                    )
                    .set_position(("center", "bottom"))
                    .set_start(start)
                    .set_end(end)
                )
                clips.append(clip)
                print(f"字幕作成成功: {text[:20]}...")
            except Exception as e:
                print(f"字幕作成エラー: {text[:20]}... - {e}")
                continue
        
        print(f"作成した字幕クリップ数: {len(clips)}")
        return clips
