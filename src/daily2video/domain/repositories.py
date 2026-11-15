from __future__ import annotations

from typing import Protocol

from .models import Article


class ArticleRepository(Protocol):
    """動画化の元になる記事を取得する契約。"""

    def latest(self) -> Article | None: ...

    def by_id(self, article_id: int) -> Article | None: ...
