from __future__ import annotations

from datetime import datetime, date, timedelta
import re
from typing import Any

import requests

from ...core.settings import get_settings
from ...domain.interfaces import ArticleRepository
from ...domain.models import Article


class EsaRestClient(ArticleRepository):
    BASE_URL = "https://api.esa.io/v1"
    PER_PAGE = 20

    def __init__(self) -> None:
        self._settings = get_settings()
        if not self._settings.esa_api_token:
            raise RuntimeError("ESA API token is not configured")
        if not self._settings.esa_team:
            raise RuntimeError("ESA team is not configured")
        self._preferred_category = (self._settings.esa_category or "").strip() or None
        raw_tags = self._settings.esa_tag or ""
        self._preferred_tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()]

    def latest(self) -> Article | None:
        target_date = self._current_date_jst()
        posts = self._fetch_posts()
        if not posts:
            print("[esa_client] category_filtered: 指定カテゴリの記事が取得できませんでした。")
            return None
        selected, _ = self._select_article(posts, target_date, context="category_filtered")
        return selected

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
        queries: list[str] = []
        if self._preferred_category:
            queries.append(f'category:"{self._preferred_category}"')
        elif self._preferred_tags:
            queries.append(self._tag_query(self._preferred_tags))

        if queries:
            params["q"] = " ".join(queries)

    def _fetch_posts(self) -> list[dict]:
        params = {
            "per_page": self.PER_PAGE,
            "sort": "created",
            "order": "desc",
            "wip": "false",
        }
        self._append_filters(params)
        response = self._request("GET", "/posts", params=params)
        return response.get("posts", [])

    @staticmethod
    def _tag_query(tags: list[str]) -> str:
        if not tags:
            return ""
        if len(tags) == 1:
            return f"tag:{tags[0]}"
        clause = " OR ".join(f"tag:{tag}" for tag in tags)
        return f"({clause})"

    def _to_article(self, raw: dict) -> Article:
        parsed_published_at = self._parse_datetime(raw.get("published_at"))
        parsed_created_at = self._parse_datetime(raw.get("created_at"))
        parsed_updated_at = self._parse_datetime(raw.get("updated_at"))

        if parsed_published_at is None:
            parsed_published_at = parsed_created_at or parsed_updated_at

        article = Article(
            article_id=raw.get("number", 0),
            title=raw.get("name", ""),
            markdown_body=raw.get("body_md", ""),
            category=raw.get("category"),
            tags=raw.get("tags", []),
            url=raw.get("url"),
            published_at=parsed_published_at,
        )
        self._persist_article_markdown(article.article_id, article.markdown_body)
        return article

    def _current_date_jst(self):
        return datetime.now(self._jst_timezone()).date()

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

        annotated: list[tuple[int, dict, date | None, tuple[int, int]]] = []
        for idx, post in enumerate(posts):
            post_date = self._extract_post_date(post)
            preference_score = self._preference_score(post)
            annotated.append((idx, post, post_date, preference_score))

        requires_preference = bool(self._preferred_category or self._preferred_tags)

        def _pick_for_date(target: date):
            candidates = [item for item in annotated if item[2] == target]
            if not candidates:
                return None
            best = max(candidates, key=lambda item: (item[3][0], item[3][1], -item[0]))
            if requires_preference and not (best[3][0] or best[3][1]):
                print(
                    f"[esa_client] {context}: 指定フィルタに一致しないものの、日付が一致する記事を使用します。",
                    f"target_date={target}",
                    f"article_id={best[1].get('number')}",
                )
            return self._to_article(best[1]), target

        result = _pick_for_date(target_date)
        if result:
            return result

        previous_day = target_date - timedelta(days=1)
        result = _pick_for_date(previous_day)
        if result:
            print(
                f"[esa_client] {context}: 当日記事が見つからなかったため前日({previous_day})の記事を使用します。"
            )
            return result

        with_dates = [item for item in annotated if item[2] is not None]
        preferred_with_dates = (
            [item for item in with_dates if item[3][0] or item[3][1]]
            if requires_preference
            else with_dates
        )
        if preferred_with_dates:
            fallback_date = max(item[2] for item in preferred_with_dates)
            fallback_candidates = [
                item for item in preferred_with_dates if item[2] == fallback_date
            ]
            best = max(fallback_candidates, key=lambda item: (item[3][0], item[3][1], -item[0]))
            print(
                f"[esa_client] {context}: 当日・前日記事が見つからず最新の対象記事を使用します。",
                f"target_date={target_date}",
                f"fallback_date={fallback_date}",
                "candidates=",
                [(post.get('number'), item_date) for _, post, item_date, _ in annotated[:5]],
            )
            return self._to_article(best[1]), fallback_date

        if with_dates:
            _, fallback_post, fallback_date, _ = max(with_dates, key=lambda item: item[2])
            print(
                f"[esa_client] {context}: 当日記事が見つからず最新日付の記事を使用します。",
                f"target_date={target_date}",
                f"fallback_date={fallback_date}",
                "candidates=",
                [(post.get('number'), item_date) for _, post, item_date, _ in annotated[:5]],
            )
            return self._to_article(fallback_post), fallback_date

        print(
            f"[esa_client] {context}: 日付情報を特定できなかったため、先頭の記事を使用します。",
            [(post.get('number'), post.get('name')) for _, post, _, _ in annotated[:3]],
        )
        first_post = annotated[0][1]
        first_date = annotated[0][2]
        return self._to_article(first_post), first_date

    def _extract_post_date(self, post: dict) -> date | None:
        # タイトルから日付を抽出（優先）
        name = post.get("name") or ""
        match = re.search(r"(20\d{2})[-/年](0?\d{1,2})[-/月](0?\d{1,2})", name)
        if match:
            year, month, day = match.groups()
            try:
                return date(int(year), int(month), int(day))
            except ValueError:
                pass
        
        # フォールバック: published_at
        published = self._parse_datetime(post.get("published_at"))
        if published:
            return published.astimezone(self._jst_timezone()).date()

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

    def _preference_score(self, post: dict) -> tuple[int, int]:
        category_match = 0
        if self._preferred_category and post.get("category") == self._preferred_category:
            category_match = 1

        tag_match = 0
        if self._preferred_tags:
            post_tags = post.get("tags") or []
            if any(tag in post_tags for tag in self._preferred_tags):
                tag_match = 1

        return category_match, tag_match

    def _persist_article_markdown(self, article_id: int, markdown_body: str) -> None:
        if not markdown_body:
            return
        try:
            path = self._settings.storage.articles_dir / f"{article_id}.md"
            path.write_text(markdown_body, encoding="utf-8")
        except OSError:
            pass
