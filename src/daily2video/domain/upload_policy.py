from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .models import Article, UploadSkipReason


@dataclass(frozen=True, slots=True)
class UploadDecision:
    allowed: bool
    skip_reason: UploadSkipReason | None = None


def decide_upload(
    *,
    article: Article,
    today: date,
    already_uploaded_today: bool,
    force_upload: bool = False,
) -> UploadDecision:
    """YouTubeへアップロードしてよいかを判断する。

    - 投稿は1日1本まで（強制指定時を除く）。
    - 記事の日付が未来の場合は投稿しない（強制指定でも投稿しない）。
    - 記事の日付が分からない場合は投稿する。
    """
    if already_uploaded_today and not force_upload:
        return UploadDecision(False, UploadSkipReason.ALREADY_UPLOADED_TODAY)

    article_date = article.effective_date()
    if article_date is None or article_date <= today:
        return UploadDecision(True)
    return UploadDecision(False, UploadSkipReason.ARTICLE_DATE_IN_FUTURE)
