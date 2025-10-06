from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List
from datetime import datetime

from ...core.openai_client import get_openai_client
from ...core.settings import get_settings
from ...domain.interfaces import MetadataGenerator, ScriptGenerator
from ...domain.models import Article, Script, ScriptLine, VideoMetadata

SCRIPT_SYSTEM_PROMPT = (
    "あなたはAIニュースを魅力的に伝える映像脚本家です。"
    "視聴者にとって分かりやすく、学びのある会話を日本語で作ってください。"
)

SCRIPT_USER_TEMPLATE = """
以下はesaで公開されたAIニュース記事です。内容を要約しつつ2人のキャラクターが丁寧に説明する台本を作成してください。

# 出力ルール
- スピーカーはAとBの2名だけに限定してください
- 各台詞は「A: ...」「B: ...」形式で1行ずつ記述してください
- 導入部でニュースの概要、続いて重要ポイント、最後に今後の展望を語ってください
- 完結した会話にしてください
- 日付は{date_str}として参照してください

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
- タグは最大10個、日本語で短くしてください
- 説明文は500文字以内を目安に自然な日本語でまとめてください
"""


class OpenAIScriptService(ScriptGenerator, MetadataGenerator):
    def __init__(self) -> None:
        self._client = get_openai_client()
        self._settings = get_settings()

    def build_script(self, article: Article) -> Script:
        date_str = self._format_date(article.published_at)
        
        response = self._client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.5,
            max_tokens=2000,
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
            max_tokens=800,
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
        pattern = re.compile(r"^(?P<speaker>A|B)[：:]\s*(?P<line>.+)$")
        lines: List[ScriptLine] = []
        for line in raw.splitlines():
            match = pattern.match(line.strip())
            if match:
                lines.append(ScriptLine(speaker=match.group("speaker"), text=match.group("line")))
        if not lines:
            lines.append(ScriptLine(speaker="ナレーター", text=raw.strip()))
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
