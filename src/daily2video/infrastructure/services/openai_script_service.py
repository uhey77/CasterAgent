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
    "視聴者にとって分かりやすく、学びのある会話を日本語で作ってください。"
)

SCRIPT_USER_TEMPLATE = """
以下はesaで公開されたAIニュース記事です。記事に記載されている**全ての研究項目（14項目全て）**を漏れなく網羅して、2人のキャラクターが項目別に整理した台本を作成してください。

# 動画構成（必須）
1. オープニング: 挨拶と日付({date_str})、今日のハイライト概要
2. 詳細なチャプター一覧: 記事に含まれる**全14項目**を番号付きで詳しく紹介（最低60秒間）
3. 各項目の詳細解説: **全14項目**を順番に詳しく解説（著者名、所属、数値、DOI含む）
4. クロージング: 全体のまとめと今後の展望

# 重要な指示（厳守）
- 記事の**全14項目**を必ず含めてください：
  * XAI分野：4項目（AD、EDCT、TextCAM、EAP-IG）
  * LLM/エージェント分野：4項目（UpSafe°C、RLAD、bBoN、Executable Counterfactuals）
  * 生成AI分野：1項目（Temporal Score Rescaling）
  * Science/Nature：2項目（DNA合成セキュリティ、HuDiff）
  * Xウォッチ：3項目（RLAD、bBoN、Executable Counterfactals）
- 各項目について著者名、所属機関、DOI、具体的数値を全て含めてください
- 記事の「📌 本日のハイライト」も必ず言及してください
- 専門用語や略語の説明も含めてください

# チャプター一覧の読み上げルール（重要）
- 「今日のトピックは全部で◯◯項目あります」と明言してください
- 各分野ごとにグループ化して紹介してください
- 「XAI分野では4つの研究、LLM/エージェント分野では4つの研究...」という形で構造化してください
- チャプター一覧だけで最低20-25行の台詞を作ってください
- 各項目の短い説明（1-2文）も含めてください

# 各項目の詳細説明ルール
- 各項目は「それでは○つ目の【正確な論文タイトル】について詳しく見ていきましょう」で開始
- 著者名、所属、投稿日、DOI、URLを必ず含める
- 研究の背景、手法、実験結果、具体的数値、意義を全て含める
- 1つの項目につき最低8-12行の詳細説明を作る

# 出力ルール
- スピーカーはAとBの2名だけに限定してください
- 各台詞は「A: ...」「B: ...」形式で1行ずつ記述してください
- 最終的に100行以上の大容量台本を作成してください

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
