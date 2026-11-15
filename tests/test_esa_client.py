from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from daily2video.infrastructure.clients.esa_client import EsaRestClient


def make_client(tmp_path) -> EsaRestClient:
    client = EsaRestClient.__new__(EsaRestClient)
    client._settings = SimpleNamespace(storage=SimpleNamespace(articles_dir=tmp_path))
    return client


def test_issue_date_comes_from_post_name(tmp_path) -> None:
    article = make_client(tmp_path)._to_article(
        {
            "number": 10,
            "name": "AI Daily 2026-11-16",
            "body_md": "## 見出し",
            "published_at": "2026-11-15T08:00:00+09:00",
        }
    )
    assert article.issue_date == date(2026, 11, 16)
    assert article.published_at is not None and article.published_at.day == 15


def test_issue_date_falls_back_to_published_timestamp(tmp_path) -> None:
    article = make_client(tmp_path)._to_article(
        {"number": 11, "name": "日付のない記事", "body_md": "", "published_at": "2026-11-15T23:30:00+09:00"}
    )
    assert article.issue_date == date(2026, 11, 15)
