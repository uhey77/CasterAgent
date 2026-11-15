from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from daily2video.application.use_cases.generate_daily_video import GenerateDailyVideoResult
from daily2video.domain.errors import ArticleNotFoundError
from daily2video.domain.models import JST, PipelineStage, PipelineStatus, VideoAsset
from daily2video.presentation import api


class StubUseCase:
    def __init__(self, outcome) -> None:
        self._outcome = outcome
        self.commands = []

    def execute(self, command):
        self.commands.append(command)
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def client_for(use_case: StubUseCase) -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_pipeline_use_case] = lambda: use_case
    return TestClient(app)


def test_run_pipeline_returns_result_as_plain_values() -> None:
    now = datetime(2026, 11, 15, 9, 0, tzinfo=JST)
    use_case = StubUseCase(
        GenerateDailyVideoResult(
            status=PipelineStatus(status=PipelineStage.UPLOADED, started_at=now, completed_at=now),
            video=VideoAsset(article_id=7, file_path=Path("data/videos/7.mp4"), duration_seconds=1.0),
            metadata=None,
            youtube_video_id="abc",
        )
    )

    response = client_for(use_case).post("/pipeline/run", json={"article_id": 7})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "uploaded"
    assert body["video_path"] == "data/videos/7.mp4"
    assert body["youtube_video_id"] == "abc"
    assert use_case.commands[0].article_id == 7


def test_business_error_maps_to_400() -> None:
    response = client_for(StubUseCase(ArticleNotFoundError())).post("/pipeline/run", json={})
    assert response.status_code == 400
    assert "対象の記事が見つかりませんでした" in response.json()["detail"]
