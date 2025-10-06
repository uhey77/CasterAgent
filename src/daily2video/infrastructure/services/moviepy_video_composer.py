from __future__ import annotations

import re
import unicodedata
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
import numpy as np

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
        
        # トピックリスト画面とオーバーレイクリップを生成
        subtitle_clips = self._build_subtitle_clips(subtitles.segments, duration)
        script_text = self._load_script_text(audio.article_id)
        topic_overlay_clips = self._build_topic_list_overlay(script_text, duration)
        
        # 全てのクリップを合成
        all_clips = [image_clip] + subtitle_clips + topic_overlay_clips
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
        for clip in topic_overlay_clips:
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

    def _build_topic_list_overlay(
        self,
        script_text: Optional[str],
        duration: float,
    ):
        """Pillowを使ってトピックリスト画像を生成し、動画冒頭にオーバーレイ"""
        try:
            # 研究項目を抽出
            research_items = self._extract_research_items(script_text)
            if not research_items:
                print("研究項目が抽出できませんでした")
                return []

            # Pillowで画像を生成
            img = Image.new('RGBA', (1920, 1080), (255, 255, 255, 242))  # 半透明の白背景
            draw = ImageDraw.Draw(img)

            # フォントを読み込み
            font_path = self._get_font_path()
            try:
                title_font = ImageFont.truetype(font_path, 70)
                number_font = ImageFont.truetype(font_path, 42)
                category_font = ImageFont.truetype(font_path, 32)
                text_font = ImageFont.truetype(font_path, 36)
            except Exception as e:
                print(f"フォント読み込みエラー: {e}")
                return []

            # タイトルを描画
            title_text = f"本日のトピック（全{len(research_items)}項目）"
            draw.text((100, 60), title_text, font=title_font, fill=(31, 42, 68))

            # 2カラムレイアウトで項目を表示
            y_offset = 160
            x_left = 100
            x_right = 960
            line_height = 65

            for idx, (category, title) in enumerate(research_items, 1):
                # 奇数は左カラム、偶数は右カラム
                x_pos = x_left if idx % 2 == 1 else x_right

                # 番号
                draw.text((x_pos, y_offset), f"{idx}.", font=number_font, fill=(30, 136, 229))

                # 分野タグ（あれば）
                text_x_offset = x_pos + 50
                if category:
                    draw.text((text_x_offset, y_offset + 2), f"[{category}]", font=category_font, fill=(255, 107, 107))
                    text_x_offset += 150

                # タイトル（長い場合は短縮）
                display_title = self._truncate_title(title, 22)
                draw.text((text_x_offset, y_offset), display_title, font=text_font, fill=(33, 33, 33))

                # 偶数番号の後に次の行へ
                if idx % 2 == 0:
                    y_offset += line_height

            # Pillowの画像をnumpy配列に変換
            img_array = np.array(img)

            # ImageClipとして作成
            display_duration = 12.0
            display_end = min(display_duration, duration)
            
            topic_clip = (
                ImageClip(img_array)
                .set_duration(display_end)
                .set_position("center")
                .set_start(0)
            )

            print(f"トピックリスト作成成功: {len(research_items)}項目")
            return [topic_clip]

        except Exception as exc:
            print(f"トピックリスト作成エラー: {exc}")
            import traceback
            traceback.print_exc()
            return []

    def _build_chapter_overlay_clips(
        self,
        segments: List[SubtitleSegment],
        duration: float,
        script_text: Optional[str],
    ):
        """互換性のため残しているが、_build_topic_list_overlayを使用"""
        return []

    def _extract_research_items(self, script_text: Optional[str]) -> List[Tuple[str, str]]:
        """スクリプトから研究項目を抽出（分野とタイトル）"""
        if not script_text:
            return []

        items: List[Tuple[str, str]] = []
        seen: set[str] = set()
        
        # **タイトル** 形式（Markdownボールド）を抽出
        for line in script_text.splitlines():
            # **で囲まれた部分を探す
            matches = re.findall(r"\*\*([^*]+)\*\*", line)
            for match in matches:
                title = match.strip()
                
                # 短すぎるもの、数字だけ、重複は除外
                if not title or len(title) < 3 or title.isdigit() or title in seen:
                    continue
                
                # よくある一般的なフレーズは除外
                skip_phrases = ["AI Daily", "こちら", "まず", "次に", "最後に", "さらに"]
                if any(phrase in title for phrase in skip_phrases):
                    continue
                
                # 分野を判定
                category = self._categorize_research(title, line)
                items.append((category, title))
                seen.add(title)
                
                if len(items) >= 20:
                    break
            
            if len(items) >= 20:
                break
        
        print(f"抽出した研究項目: {len(items)}件")
        for idx, (cat, title) in enumerate(items, 1):
            print(f"  {idx}. [{cat}] {title[:30]}...")
        
        return items

    def _categorize_research(self, title: str, line: str) -> str:
        """研究の分野を判定"""
        line_lower = line.lower()
        title_lower = title.lower()
        
        # XAI関連
        if any(keyword in line_lower or keyword in title_lower for keyword in 
               ["xai", "explainable", "interpretability", "activation", "deactivation", "eap", "textcam", "edct"]):
            return "XAI"
        
        # LLM/エージェント関連
        if any(keyword in line_lower or keyword in title_lower for keyword in 
               ["llm", "エージェント", "agent", "rlhf", "grpo", "dpo", "policy", "m2po", "sirl"]):
            return "LLM"
        
        # 生成AI関連
        if any(keyword in line_lower or keyword in title_lower for keyword in 
               ["生成", "diffusion", "generation", "temporal", "score", "flow", "bridge"]):
            return "生成AI"
        
        # Science/Nature関連
        if any(keyword in line_lower or keyword in title_lower for keyword in 
               ["science", "nature", "bio", "antibod", "protein", "hudiff", "dna"]):
            return "Science"
        
        # Xウォッチ
        if "ウォッチ" in line or "watch" in line_lower or "rlad" in title_lower or "bbon" in title_lower or "executable" in title_lower:
            return "X"
        
        return ""

    def _truncate_title(self, title: str, max_length: int) -> str:
        """タイトルが長い場合は短縮"""
        if len(title) <= max_length:
            return title
        return title[:max_length] + "..."

    def _load_script_text(self, article_id: int) -> Optional[str]:
        script_path = self._settings.storage.scripts_dir / f"{article_id}.txt"
        try:
            return script_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"スクリプトファイルが見つかりません: {script_path}")
            return None

    def _get_font_path(self) -> str:
        """日本語フォントのパスを取得"""
        font_candidates = [
            "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc", 
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/ee89e7987a76cc8cfdff36c96bd7bc77655b343e.asset/AssetData/YuGothic-Medium.otf",
        ]
        
        from pathlib import Path
        for font in font_candidates:
            if Path(font).exists():
                print(f"使用フォント: {font}")
                return font
        
        # デフォルト
        return "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc"

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
