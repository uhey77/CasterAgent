from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from ...core.settings import get_settings
from ...domain.interfaces import ArticleRepository
from ...domain.models import Article


class EsaRestClient(ArticleRepository):
    BASE_URL = "https://api.esa.io/v1"

    def __init__(self) -> None:
        self._settings = get_settings()
        if not self._settings.esa_api_token:
            raise RuntimeError("ESA API token is not configured")
        if not self._settings.esa_team:
            raise RuntimeError("ESA team is not configured")

    def latest(self) -> Article | None:
        params = {
            "per_page": 1,
            "sort": "created",
            "order": "desc",
        }
        self._append_filters(params)
        response = self._request("GET", "/posts", params=params)
        posts = response.get("posts", [])
        if not posts:
            return None
        return self._to_article(posts[0])

    def by_id(self, article_id: int) -> Article | None:
        response = self._request("GET", f"/posts/{article_id}")
        return self._to_article(response) if response else None

    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        headers = {
            "Authorization": f"Bearer {self._settings.esa_api_token}",
            "Content-Type": "application/json",
        }
        url = f"{self.BASE_URL}/teams/{self._settings.esa_team}{path}"
        response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        response.raise_for_status()
        return response.json()

    def _append_filters(self, params: dict[str, Any]) -> None:
        if self._settings.esa_category:
            params["category"] = self._settings.esa_category
        if self._settings.esa_tag:
            params["q"] = f"tag:{self._settings.esa_tag}"

    def _to_article(self, raw: dict) -> Article:
        published_at = raw.get("published_at")
        parsed_published_at = (
            datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            if published_at
            else None
        )
        return Article(
            article_id=raw.get("number", 0),
            title=raw.get("name", ""),
            markdown_body=raw.get("body_md", ""),
            category=raw.get("category"),
            tags=raw.get("tags", []),
            url=raw.get("url"),
            published_at=parsed_published_at,
        )
