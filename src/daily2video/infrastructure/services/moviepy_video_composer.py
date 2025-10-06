from __future__ import annotations

import re
from typing import List, Tuple

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
            .resize((1920, 1080))
            .set_position("center")
        )
        
        # チャプター画面とオーバーレイクリップを生成
        subtitle_clips = self._build_subtitle_clips(subtitles.segments, duration)
        chapter_overlay_clips = self._build_chapter_overlay_clips(subtitles.segments, duration)
        
        # 全てのクリップを合成
        all_clips = [image_clip] + subtitle_clips + chapter_overlay_clips
        video_clip = CompositeVideoClip(all_clips)
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
        for clip in chapter_overlay_clips:
            clip.close()

        return VideoAsset(article_id=audio.article_id, file_path=output_path, duration_seconds=duration)

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

    def _build_chapter_overlay_clips(self, segments: List[SubtitleSegment], duration: float):
        """YouTubeチャプター風のオーバーレイクリップを生成"""
        clips = []
        selected_font = self._get_font()
        
        if selected_font is None:
            return []
        
        # チャプター一覧の範囲を特定
        chapter_range = self._find_chapter_list_range(segments)
        if not chapter_range:
            return []
        
        start_time, end_time = chapter_range
        
        # チャプターリストを抽出
        chapters = self._extract_chapters(segments)
        if not chapters:
            return []
        
        try:
            # 背景クリップ（青いグラデーション背景）
            background_clip = (
                TextClip("", fontsize=1)
                .on_color(
                    size=(1920, 1080),
                    color=(15, 25, 50),  # 濃い青背景
                    col_opacity=0.95
                )
                .set_position("center")
                .set_start(start_time)
                .set_end(end_time)
            )
            clips.append(background_clip)
            
            # メインタイトル
            title_clip = (
                TextClip(
                    "Chapters:",
                    fontsize=80,
                    font=selected_font,
                    color="white"
                )
                .set_position((100, 80))
                .set_start(start_time)
                .set_end(end_time)
            )
            clips.append(title_clip)
            
            # チャプターリスト（左側に時間、右側にタイトル）
            y_offset = 180
            for i, (time_str, chapter_title) in enumerate(chapters):
                if i > 10:  # 最大11項目まで表示
                    break
                
                # タイムスタンプ（青色）
                time_clip = (
                    TextClip(
                        time_str,
                        fontsize=50,
                        font=selected_font,
                        color="#4A9EFF"  # 青色
                    )
                    .set_position((100, y_offset))
                    .set_start(start_time)
                    .set_end(end_time)
                )
                clips.append(time_clip)
                
                # チャプタータイトル
                title_text = f"- {chapter_title}"
                chapter_clip = (
                    TextClip(
                        title_text,
                        fontsize=45,
                        font=selected_font,
                        color="white",
                        method="caption",
                        size=(1400, None)
                    )
                    .set_position((250, y_offset))
                    .set_start(start_time)
                    .set_end(end_time)
                )
                clips.append(chapter_clip)
                
                y_offset += 70
            
            print(f"チャプター画面作成成功: {len(chapters)}項目")
            
        except Exception as e:
            print(f"チャプター画面作成エラー: {e}")
        
        return clips

    def _find_chapter_list_range(self, segments: List[SubtitleSegment]) -> Tuple[float, float] | None:
        """チャプター一覧の時間範囲を特定"""
        start_patterns = [
            r"今日のトピック",
            r"全部で14項目",
            r"項目があります",
            r"チャプター"
        ]
        
        end_patterns = [
            r"それでは.*つ目",
            r"詳細を見て",
            r"始めていき"
        ]
        
        start_time = None
        end_time = None
        
        for segment in segments:
            if any(re.search(pattern, segment.text) for pattern in start_patterns):
                start_time = segment.start_seconds
                break
        
        if start_time is not None:
            for segment in segments:
                if segment.start_seconds > start_time + 10:  # 最低10秒後
                    if any(re.search(pattern, segment.text) for pattern in end_patterns):
                        end_time = segment.start_seconds
                        break
            
            if end_time is None:
                end_time = start_time + 60  # 60秒間表示
        
        if start_time is not None and end_time is not None:
            return (start_time, end_time)
        
        return None

    def _extract_chapters(self, segments: List[SubtitleSegment]) -> List[Tuple[str, str]]:
        """チャプターリスト（時間とタイトル）を抽出"""
        chapters = []
        
        # 想定されるチャプター構成
        chapter_titles = [
            "Intro",
            "XAI - Activation-Deactivation", 
            "XAI - EDCT for VLM",
            "XAI - TextCAM",
            "XAI - EAP-IG Analysis",
            "LLM - UpSafe°C",
            "LLM - RLAD",
            "LLM - bBoN Agents",
            "LLM - Executable Counterfactuals",
            "Generative AI - Temporal Score Rescaling",
            "Science/Nature Research",
            "Summary & Future"
        ]
        
        # 時間を推定（均等分割）
        total_duration = segments[-1].end_seconds if segments else 300
        intro_time = 0
        chapter_duration = (total_duration - 60) / len(chapter_titles)  # 60秒はイントロとまとめ
        
        for i, title in enumerate(chapter_titles):
            time_seconds = intro_time + (i * chapter_duration)
            minutes = int(time_seconds // 60)
            seconds = int(time_seconds % 60)
            time_str = f"{minutes:02d}:{seconds:02d}"
            chapters.append((time_str, title))
        
        return chapters

    def _get_font(self):
        """利用可能な日本語フォントを取得"""
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
