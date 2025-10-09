from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Tuple
from datetime import datetime

from ...core.openai_client import get_openai_client
from ...core.settings import get_settings
from ...domain.interfaces import MetadataGenerator, ScriptGenerator
from ...domain.models import Article, Script, ScriptLine, VideoMetadata

SCRIPT_SYSTEM_PROMPT = (
    "あなたはAIニュースを魅力的に伝える映像脚本家です。\n"
    "視聴者にとって分かりやすく、学びのある会話を日本語で作ってください。\n"
    "目次画像に合わせたトーク構成や、話し言葉と画面上の情報の役割分担を意識してください。"
)

SCRIPT_USER_TEMPLATE = """
以下はesaで公開されたAIニュース記事です。記事に記載されている研究項目をもとに、2人のキャラクターが会話する台本を作成してください。

# 動画構成（必須）
1. オープニング: 挨拶と日付({date_str})、今日のハイライト概要
2. トピック概要: 目次画像に合わせて「今日のトピックは全部で◯◯項目。本日は◯◯が注目です。」と述べる程度にとどめ、個別タイトルは列挙しない
3. 各項目の詳細解説: 記事に含まれるすべての研究項目を順番に詳しく解説（研究の背景・手法・結果・示唆を中心に、書誌情報は読み上げない）
4. クロージング: 全体のまとめと今後の展望

# 重要な指示（厳守）
- トピック概要パートでは個別タイトルや番号を読み上げない。項目数と注目テーマのみ、自然な会話で触れること
- 「本日は◯◯が注目です」「詳しくは画像でチェックしてください」のような一言を添えて、目次画像の存在を言及する
- 詳細解説パートでは各論文の要点（課題、アプローチ、主要な成果、なぜ重要か）を分かりやすく説明する
- 著者名・所属・投稿日・DOIなどの書誌情報は口頭で読み上げない。その代わりに節の冒頭か末尾で「書誌情報は概要欄にまとめています」と伝える
- 記事の「📌 本日のハイライト」があれば冒頭で触れる
- 専門用語や略語の説明も含め、視聴者が理解しやすい比喩や補足を加える

# 各項目の詳細説明ルール
- 各項目は「それでは○つ目の【正確な論文タイトル】について詳しく見ていきましょう」で開始し、その後は口頭での解説に集中する
- 研究の背景、提案手法、実験結果・数値、そこから導かれる示唆をバランス良く含める
- 書誌情報に触れる場合は「著者名などの詳しい情報は概要欄へ」といった案内に留める
- 1つの項目につき最低6行の台詞を作る

# 出力ルール
- スピーカーはAとBの2名だけに限定してください
- 各台詞は「A: ...」「B: ...」形式で1行ずつ記述してください
- 最終的に70行以上の台本を作成してください

# 記事情報
- 記事タイトル: {title}
- 公開日: {date_str}

# 記事本文（Markdown）
{body}
"""

METADATA_SYSTEM_PROMPT = (
    "You are an expert Japanese YouTube strategist generating SEO friendly metadata for technology news."
)

METADATA_USER_TEMPLATE = """
以下のニュース記事と台本を参考に、YouTube動画のメタデータをJSON形式で作成してください。

# 記事情報
- 記事タイトル: {title}
- 公開日: {date_str}

# 台本
{script}

# 要件
- JSONオブジェクトを返してください
- `title`, `description`, `tags`(配列), `category_id`(文字列), `privacy_status`(public|unlisted|private) を含めてください
- タイトルには{date_str}の日付を含めてください
- 説明文には記事の出典URLを含めてください（URLが分からない場合は省略）
- 説明文には動画内で紹介した各研究の書誌情報（タイトル、著者、所属、掲載先/投稿日、DOIやURLなど判明している項目）を箇条書きでまとめてください
- 説明文には書誌情報に続いて動画の概要とハイライトを200〜400文字で添えてください
- タグは最大10個、日本語で短くしてください
"""


class OpenAIScriptService(ScriptGenerator, MetadataGenerator):
    def __init__(self) -> None:
        self._client = get_openai_client()
        self._settings = get_settings()

    def build_script(self, article: Article) -> Script:
        date_str = self._format_date(article.published_at)
        
        response = self._client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            # max_tokens=5000,
            messages=[
                {"role": "system", "content": SCRIPT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": SCRIPT_USER_TEMPLATE.format(
                        title=article.title,
                        body=article.markdown_body,
                        date_str=date_str,
                    ),
                },
            ],
        )
        content = response.choices[0].message.content.strip()
        lines = self._parse_script(content)
        script = Script(article_id=article.article_id, lines=lines, raw_text=content)
        script.file_path = self._persist_script(script)
        return script

    def build_metadata(self, article: Article, script: Script) -> VideoMetadata:
        date_str = self._format_date(article.published_at)
        
        response = self._client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            # max_tokens=800,
            messages=[
                {"role": "system", "content": METADATA_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": METADATA_USER_TEMPLATE.format(
                        title=article.title,
                        script=script.raw_text,
                        date_str=date_str,
                    ),
                },
            ],
        )
        payload = self._parse_metadata_json(response.choices[0].message.content)
        tags = payload.get("tags", [])
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
        if not isinstance(tags, list):
            tags = []
        metadata = VideoMetadata(
            article_id=article.article_id,
            title=payload.get("title", f"{article.title} - {date_str}"),
            description=payload.get("description", article.markdown_body[:4000]),
            tags=tags,
            category_id=str(payload.get("category_id", "28")),
            privacy_status=str(payload.get("privacy_status", "public")),
        )
        metadata.file_path = self._persist_metadata(metadata, article)
        return metadata

    @staticmethod
    def _parse_script(raw: str) -> List[ScriptLine]:
        cleaned = raw.strip()
        if cleaned.startswith("```") and cleaned.endswith("```"):
            cleaned = cleaned.split("\n", 1)[-1].rsplit("\n", 1)[0]

        pattern = re.compile(r"^(?P<speaker>A|B)[：:]\s*(?P<line>.+)$")
        lines: List[ScriptLine] = []
        for line in cleaned.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            match = pattern.match(stripped)
            if match:
                lines.append(ScriptLine(speaker=match.group("speaker"), text=match.group("line")))
            elif lines:
                existing = lines[-1].text
                lines[-1].text = f"{existing}\n{stripped}" if existing else stripped
            else:
                lines.append(ScriptLine(speaker="ナレーター", text=stripped))

        if not lines:
            lines.append(ScriptLine(speaker="ナレーター", text=cleaned))
        return lines

    @staticmethod
    def _parse_metadata_json(raw: str) -> dict:
        cleaned = raw.strip()
        if cleaned.startswith("```") and cleaned.endswith("```"):
            cleaned = cleaned.split("\n", 1)[-1].rsplit("\n", 1)[0]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive fallback
            raise ValueError(f"Could not parse metadata JSON: {exc}") from exc

    def _persist_metadata(self, metadata: VideoMetadata, article: Article) -> Path:
        path = self._settings.storage.metadata_dir / f"{article.article_id}.json"
        payload = {
            "title": metadata.title,
            "description": metadata.description,
            "tags": metadata.tags,
            "category_id": metadata.category_id,
            "privacy_status": metadata.privacy_status,
            "language": metadata.language,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _persist_script(self, script: Script) -> Path:
        path = self._settings.storage.scripts_dir / f"{script.article_id}.txt"
        path.write_text(script.raw_text, encoding="utf-8")
        return path

    def _format_date(self, published_at: datetime | None) -> str:
        """記事の日付を日本語形式でフォーマット"""
        if published_at:
            return published_at.strftime("%Y年%m月%d日")
        else:
            return datetime.now().strftime("%Y年%m月%d日")
