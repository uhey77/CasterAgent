from __future__ import annotations

import re
import unicodedata
import subprocess
from typing import List, Tuple, Optional
from pathlib import Path
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

        # トピックリスト画像を生成
        script_text = self._load_script_text(audio.article_id)
        topic_image_path = self._create_topic_list_image(audio.article_id, script_text)
        
        # FFmpegでトピック画像をオーバーレイ
        if topic_image_path and topic_image_path.exists():
            self._overlay_topic_image_with_ffmpeg(temp_output_path, topic_image_path, final_output_path, duration)
            # 一時ファイルを削除
            temp_output_path.unlink()
        else:
            # トピック画像がない場合は一時ファイルをリネーム
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

    def _create_topic_list_image(
        self,
        article_id: int,
        script_text: Optional[str],
    ) -> Optional[Path]:
        """Pillowを使ってトピックリスト画像を生成"""
        try:
            # 研究項目を抽出
            research_items = self._extract_research_items(script_text)
            if not research_items:
                print("研究項目が抽出できませんでした")
                return None

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
                return None

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

            # 画像を保存
            output_path = self._settings.storage.images_dir / f"{article_id}_topics.png"
            img.save(str(output_path))

            print(f"トピックリスト画像作成成功: {output_path}")
            return output_path

        except Exception as exc:
            print(f"トピックリスト画像作成エラー: {exc}")
            import traceback
            traceback.print_exc()
            return None

    def _overlay_topic_image_with_ffmpeg(
        self,
        input_video: Path,
        topic_image: Path,
        output_video: Path,
        duration: float,
    ) -> None:
        """FFmpegでトピック画像を動画の冒頭にオーバーレイ"""
        try:
            # 表示時間: 冒頭12秒
            display_duration = min(12.0, duration)
            
            # FFmpegコマンドを構築
            cmd = [
                'ffmpeg',
                '-i', str(input_video),
                '-i', str(topic_image),
                '-filter_complex',
                f"[0:v][1:v] overlay=0:0:enable='between(t,0,{display_duration})'",
                '-c:a', 'copy',  # 音声は再エンコードせずコピー
                '-y',  # 上書き
                str(output_video)
            ]
            
            print(f"FFmpegでトピック画像をオーバーレイ中...")
            print(f"コマンド: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            print(f"トピック画像のオーバーレイ完了: {output_video}")
            
        except subprocess.CalledProcessError as e:
            print(f"FFmpegエラー: {e}")
            print(f"stdout: {e.stdout}")
            print(f"stderr: {e.stderr}")
            # エラーの場合は元の動画をコピー
            import shutil
            shutil.copy(str(input_video), str(output_video))
        except Exception as e:
            print(f"オーバーレイエラー: {e}")
            import shutil
            shutil.copy(str(input_video), str(output_video))

    def _extract_research_items(self, script_text: Optional[str]) -> List[Tuple[str, str]]:
        """スクリプトから研究項目を抽出（分野とタイトル）"""
        if not script_text:
            return []

        items: List[Tuple[str, str]] = []
        seen: set[str] = set()
        
        # 「タイトル」形式（日本語鍵括弧）と **タイトル** 形式（Markdownボールド）の両方を抽出
        for line in script_text.splitlines():
            # 「」で囲まれた部分を探す
            matches_jp = re.findall(r"「([^」]+)」", line)
            # **で囲まれた部分も探す
            matches_md = re.findall(r"\*\*([^*]+)\*\*", line)
            
            # 両方のマッチを統合
            matches = matches_jp + matches_md
            
            for match in matches:
                title = match.strip()
                
                # 短すぎるもの、数字だけ、重複は除外
                if not title or len(title) < 3 or title.isdigit() or title in seen:
                    continue
                
                # よくある一般的なフレーズは除外
                skip_phrases = [
                    "AI Daily", "こちら", "まず", "次に", "最後に", "さらに",
                    "Bridge", "GRPO", "M2PO", "HuDiff"  # ハイライト部分の短縮形は除外
                ]
                # ただし、長いタイトル（括弧付き等）は含める
                if any(phrase == title for phrase in skip_phrases):
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
