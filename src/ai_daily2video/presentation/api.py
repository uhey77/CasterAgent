from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..application.use_cases.generate_daily_video import (
    GenerateDailyVideo,
    GenerateDailyVideoInput,
    GenerateDailyVideoResult,
)
from ..domain.models import PipelineError
from .dependencies import get_pipeline_use_case

router = APIRouter()


class PipelineRequest(BaseModel):
    article_id: Optional[int] = Field(default=None, description="esaの記事ID。指定がない場合は最新記事を取得")


class PipelineResponse(BaseModel):
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    video_path: Optional[str]
    metadata_path: Optional[str]
    youtube_video_id: Optional[str]
    notes: list[str] = Field(default_factory=list)

    @classmethod
    def from_result(cls, result: GenerateDailyVideoResult) -> "PipelineResponse":
        status = result.status
        video_path = str(result.video.file_path) if result.video else None
        metadata_path = str(result.metadata.file_path) if result.metadata and result.metadata.file_path else None
        return cls(
            status=status.status,
            started_at=status.started_at,
            completed_at=status.completed_at,
            notes=status.notes,
            video_path=video_path,
            metadata_path=metadata_path,
            youtube_video_id=result.youtube_video_id,
        )


@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@router.post("/pipeline/run", response_model=PipelineResponse)
def trigger_pipeline(
    request: PipelineRequest,
    pipeline: GenerateDailyVideo = Depends(get_pipeline_use_case),
) -> PipelineResponse:
    try:
        result = pipeline.execute(GenerateDailyVideoInput(article_id=request.article_id))
    except PipelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return PipelineResponse.from_result(result)
