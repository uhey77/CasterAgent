from __future__ import annotations

import json
from datetime import date

from daily2video.domain.models import VideoMetadata
from daily2video.infrastructure.services.metadata_store import JsonMetadataStore
from daily2video.infrastructure.services.upload_history import JsonUploadHistory


def test_upload_history_remembers_only_the_marked_day(tmp_path) -> None:
    history = JsonUploadHistory(tmp_path / "state")
    day = date(2026, 11, 15)
    assert not history.has_uploaded_on(day)

    history.mark_uploaded(day)

    assert history.has_uploaded_on(day)
    assert not history.has_uploaded_on(date(2026, 11, 16))
    # 既存の last_upload.json と同じ形式であること
    assert json.loads((tmp_path / "state" / "last_upload.json").read_text()) == {"date": "2026-11-15"}


def test_upload_history_treats_broken_marker_as_not_uploaded(tmp_path) -> None:
    (tmp_path / "last_upload.json").write_text("{broken")
    assert not JsonUploadHistory(tmp_path).has_uploaded_on(date(2026, 11, 15))


def test_metadata_store_writes_back_to_assigned_file(tmp_path) -> None:
    path = tmp_path / "1.json"
    metadata = VideoMetadata(
        article_id=1, title="AI Daily—2026-11-15", description="d", tags=["AI"], file_path=path
    )
    metadata.thumbnail_path = tmp_path / "thumb.png"

    JsonMetadataStore().save(metadata)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["title"] == "AI Daily—2026-11-15"
    assert saved["thumbnail_path"] == str(tmp_path / "thumb.png")


def test_metadata_store_ignores_metadata_without_file() -> None:
    JsonMetadataStore().save(VideoMetadata(article_id=1, title="t", description="d", tags=[]))
