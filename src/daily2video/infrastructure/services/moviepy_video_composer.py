from __future__ import annotations

from typing import List
from pathlib import Path

from moviepy.editor import AudioFileClip, CompositeVideoClip, ImageClip, TextClip

from ...core.settings import get_settings
from ...domain.interfaces import VideoComposer
from ...domain.models import AudioAsset, GeneratedImage, SubtitleFile, SubtitleSegment, VideoAsset
from .topic_overlay import build_topic_overlay, overlay_topic_image


class MoviePyVideoComposer(VideoComposer):
    def __init__(self) -> None:
        self._settings = get_settings()

    def compose(
        self,
        audio: AudioAsset,
        subtitles: SubtitleFile,
        background: GeneratedImage,
    ) -> VideoAsset:
        temp_output_path = self._settings.storage.videos_dir / f"{audio.article_id}_temp.mp4"
        final_output_path = self._settings.storage.videos_dir / f"{audio.article_id}.mp4"

        audio_clip = AudioFileClip(str(audio.file_path))
        duration = audio_clip.duration
        
        # 16:9アスペクト比（1920x1080）に強制変更
        image_clip = (
            ImageClip(str(background.file_path))
            .set_duration(duration)
            .resize((1920, 1080))
            .set_position("center")
        )
        
        # 字幕クリップを生成
        subtitle_clips = self._build_subtitle_clips(subtitles.segments, duration)
        
        # 全てのクリップを合成（トピックリストはFFmpegで後から追加）
        all_clips = [image_clip] + subtitle_clips
        video_clip = CompositeVideoClip(all_clips)
        final_clip = video_clip.set_audio(audio_clip)

        # まず一時ファイルとして動画を生成
        final_clip.write_videofile(
            str(temp_output_path),
            codec="libx264",
            audio_codec="aac",
            fps=30,
            bitrate="4000k",
            threads=4,
            temp_audiofile=str(temp_output_path.with_suffix(".temp.m4a")),
            remove_temp=True,
        )

        audio_clip.close()
        image_clip.close()
        final_clip.close()
        for clip in subtitle_clips:
            clip.close()

        overlay_spec = build_topic_overlay(
            self._settings,
            audio.article_id,
            subtitles.segments,
            duration,
        )

        if overlay_spec:
            try:
                overlay_topic_image(temp_output_path, overlay_spec, final_output_path, duration)
                temp_output_path.unlink(missing_ok=True)
            except Exception as exc:
                print(f"トピック画像オーバーレイでエラー: {exc}")
                temp_output_path.rename(final_output_path)
        else:
            temp_output_path.rename(final_output_path)

        return VideoAsset(article_id=audio.article_id, file_path=final_output_path, duration_seconds=duration)

    def _build_subtitle_clips(self, segments: List[SubtitleSegment], duration: float):
        clips = []
        selected_font = self._get_font()
        
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
                        size=(1600, None),
                    )
                    .on_color(
                        size=(1920, 200),
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


    def _get_font(self):
        """利用可能な日本語フォントを取得（字幕用）"""
        font_candidates = [
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc", 
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/ee89e7987a76cc8cfdff36c96bd7bc77655b343e.asset/AssetData/YuGothic-Medium.otf",
            None
        ]
        
        for font in font_candidates:
            try:
                test_clip = TextClip("テスト日本語", fontsize=20, font=font, color="white")
                test_clip.close()
                print(f"使用フォント: {font}")
                return font
            except Exception as e:
                print(f"フォント '{font}' は使用できません: {e}")
                continue
        
        return None
