from __future__ import annotations

import json
from pathlib import Path

from ...application.ports import MetadataStore
from ...domain.models import VideoMetadata


def write_metadata_file(metadata: VideoMetadata, path: Path) -> None:
    payload = {
        "title": metadata.title,
        "description": metadata.description,
        "tags": metadata.tags,
        "category_id": metadata.category_id,
        "privacy_status": metadata.privacy_status,
        "language": metadata.language,
    }
    if metadata.thumbnail_path:
        payload["thumbnail_path"] = str(metadata.thumbnail_path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class JsonMetadataStore(MetadataStore):
    """メタデータを、生成時に割り当てられたJSONファイルへ書き戻す。"""

    def save(self, metadata: VideoMetadata) -> None:
        if metadata.file_path:
            write_metadata_file(metadata, metadata.file_path)
