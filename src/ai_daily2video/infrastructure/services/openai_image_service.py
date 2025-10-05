from __future__ import annotations

import base64
from pathlib import Path

import requests

from ...core.openai_client import get_openai_client
from ...core.settings import get_settings
from ...domain.interfaces import BackgroundImageGenerator
from ...domain.models import Article, GeneratedImage

PROMPT_TEMPLATE = """
Create a calm, modern illustration for a Japanese technology news video background.
The scene should feature a softly lit workspace with futuristic elements, rendered in lo-fi anime style.
Include subtle blue gradients and abstract visuals suggesting artificial intelligence innovation.
No text overlays.
Title of the news article for inspiration: "{title}".
"""


class OpenAIImageService(BackgroundImageGenerator):
    def __init__(self) -> None:
        self._client = get_openai_client()
        self._settings = get_settings()

    def create_image(self, article: Article) -> GeneratedImage:
        target_path = self._settings.storage.images_dir / f"{article.article_id}.png"
        if target_path.exists():
            return GeneratedImage(article_id=article.article_id, file_path=target_path)

        prompt = PROMPT_TEMPLATE.format(title=article.title)
        response = self._client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        # URLから画像をダウンロード
        image_response = requests.get(image_url)
        image_bytes = image_response.content
        target_path.write_bytes(image_bytes)
        return GeneratedImage(article_id=article.article_id, file_path=target_path)
