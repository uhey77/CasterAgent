from __future__ import annotations

from datetime import UTC, date, datetime

from daily2video.domain.models import JST, Article, UploadSkipReason, VideoMetadata
from daily2video.domain.upload_policy import decide_upload

TODAY = date(2026, 11, 15)


def article(published_at: datetime | None = None, issue_date: date | None = None) -> Article:
    return Article(
        article_id=1, title="t", markdown_body="b", published_at=published_at, issue_date=issue_date
    )


def metadata(title: str) -> VideoMetadata:
    return VideoMetadata(article_id=1, title=title, description="d", tags=[])


def decide(**overrides):
    params = dict(article=article(), today=TODAY, already_uploaded_today=False)
    params.update(overrides)
    return decide_upload(**params)


def test_allows_article_without_published_date() -> None:
    assert decide().allowed


def test_allows_past_and_same_day_article() -> None:
    assert decide(article=article(datetime(2026, 11, 13, tzinfo=JST))).allowed
    assert decide(article=article(datetime(2026, 11, 15, 23, 59, tzinfo=JST))).allowed


def test_blocks_future_article() -> None:
    decision = decide(article=article(datetime(2026, 11, 16, tzinfo=JST)))
    assert not decision.allowed
    assert decision.skip_reason is UploadSkipReason.ARTICLE_DATE_IN_FUTURE


def test_published_date_is_compared_in_jst() -> None:
    # UTCでは11/15 15:30だが、日本時間では翌16日
    published = datetime(2026, 11, 15, 15, 30, tzinfo=UTC)
    assert not decide(article=article(published)).allowed


def test_issue_date_takes_precedence_over_published_timestamp() -> None:
    # 翌日分の記事を前日のうちに公開したケース：公開時刻は過去でも、記事の日付は未来
    prepared_early = article(datetime(2026, 11, 15, 8, 0, tzinfo=JST), issue_date=date(2026, 11, 16))
    decision = decide(article=prepared_early)
    assert not decision.allowed
    assert decision.skip_reason is UploadSkipReason.ARTICLE_DATE_IN_FUTURE

    # 逆に、過去日付の記事を今日公開し直した場合は投稿できる
    republished = article(datetime(2026, 11, 15, 8, 0, tzinfo=JST), issue_date=date(2026, 11, 14))
    assert decide(article=republished).allowed


def test_force_upload_does_not_override_future_article() -> None:
    decision = decide(article=article(issue_date=date(2026, 11, 16)), force_upload=True)
    assert not decision.allowed
    assert decision.skip_reason is UploadSkipReason.ARTICLE_DATE_IN_FUTURE


def test_only_one_upload_per_day_unless_forced() -> None:
    decision = decide(already_uploaded_today=True)
    assert not decision.allowed
    assert decision.skip_reason is UploadSkipReason.ALREADY_UPLOADED_TODAY
    assert decide(already_uploaded_today=True, force_upload=True).allowed


def test_daily_title_round_trips_through_title_date() -> None:
    meta = metadata("何かのタイトル")
    assert meta.title_date() is None
    meta.apply_daily_title(TODAY)
    assert meta.title == "AI Daily—2026-11-15"
    assert meta.title_date() == TODAY
    assert metadata("AI Daily—2026-13-40").title_date() is None
