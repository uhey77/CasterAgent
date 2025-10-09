from __future__ import annotations

from datetime import datetime, date
import re
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
        base_params = {
            "per_page": 10,
            "sort": "created",
            "order": "desc",
            "wip": "false",
        }
        params = dict(base_params)
        self._append_filters(params)

        response = self._request("GET", "/posts", params=params)
        posts = response.get("posts", [])
        target_date = self._current_date_jst()

        selected, selected_date = self._select_article(posts, target_date, context="filtered")
        if selected and selected_date == target_date:
            return selected
        if selected and selected_date is not None:
            print(
                "[esa_client]",
                "フィルタ適用時に当日と異なる記事が見つかったため、フィルタ無しで再取得します。",
                f"target_date={target_date}",
                f"selected_date={selected_date}",
                f"article_id={selected.article_id}",
            )

        print("[esa_client] 指定したカテゴリ/タグでは当日記事が見つからなかったためフィルタ無しで再取得します。")
        response = self._request("GET", "/posts", params=base_params)
        posts_unfiltered = response.get("posts", [])
        selected, _ = self._select_article(posts_unfiltered, target_date, context="unfiltered")
        if selected:
            return selected

        return None

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
        parsed_published_at = self._parse_datetime(raw.get("published_at"))
        parsed_created_at = self._parse_datetime(raw.get("created_at"))
        parsed_updated_at = self._parse_datetime(raw.get("updated_at"))

        if parsed_published_at is None:
            parsed_published_at = parsed_created_at or parsed_updated_at

        return Article(
            article_id=raw.get("number", 0),
            title=raw.get("name", ""),
            markdown_body=raw.get("body_md", ""),
            category=raw.get("category"),
            tags=raw.get("tags", []),
            url=raw.get("url"),
            published_at=parsed_published_at,
        )

    def _current_date_jst(self):
        return datetime.utcnow().astimezone(self._jst_timezone()).date()

    @staticmethod
    def _jst_timezone():
        from datetime import timezone, timedelta

        return timezone(timedelta(hours=9))

    def _date_in_jst(self, dt: datetime | None):
        if not dt:
            return None
        return dt.astimezone(self._jst_timezone()).date()

    def _select_article(
        self,
        posts: list[dict],
        target_date,
        *,
        context: str,
    ) -> tuple[Article | None, date | None]:
        if not posts:
            print(f"[esa_client] {context}: 投稿が取得できませんでした")
            return None, None

        annotated: list[tuple[dict, date | None]] = []
        for post in posts:
            post_date = self._extract_post_date(post)
            annotated.append((post, post_date))
            if post_date == target_date:
                return self._to_article(post), post_date

        with_dates = [item for item in annotated if item[1] is not None]
        if with_dates:
            fallback_post, fallback_date = max(with_dates, key=lambda item: item[1])
            print(
                f"[esa_client] {context}: 当日記事が見つからず最新日付の記事を使用します。",
                f"target_date={target_date}",
                f"fallback_date={fallback_date}",
                "candidates=",
                [(post.get('number'), item_date) for post, item_date in annotated[:5]],
            )
            return self._to_article(fallback_post), fallback_date

        print(
            f"[esa_client] {context}: 日付情報を特定できなかったため、先頭の記事を使用します。",
            [(post.get('number'), post.get('name')) for post, _ in annotated[:3]],
        )
        first_post, first_date = annotated[0]
        return self._to_article(first_post), first_date

    def _extract_post_date(self, post: dict) -> date | None:
        published = self._parse_datetime(post.get("published_at"))
        if published:
            return published.astimezone(self._jst_timezone()).date()

        name = post.get("name") or ""
        match = re.search(r"(20\\d{2})[-/年](\\d{2})[-/月](\\d{2})", name)
        if match:
            year, month, day = match.groups()
            try:
                return date(int(year), int(month), int(day))
            except ValueError:
                pass

        created = self._parse_datetime(post.get("created_at"))
        if created:
            return created.astimezone(self._jst_timezone()).date()

        updated = self._parse_datetime(post.get("updated_at"))
        if updated:
            return updated.astimezone(self._jst_timezone()).date()

        return None

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
