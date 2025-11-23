from __future__ import annotations

import argparse
import sys

from daily2video.application.services.pipeline_service import build_pipeline_use_case
from daily2video.application.use_cases.generate_daily_video import GenerateDailyVideoInput
from daily2video.domain.models import PipelineError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Dailyの動画生成パイプラインを1回だけ実行する開発用コマンド",
    )
    parser.add_argument(
        "--article-id",
        type=int,
        default=None,
        help="esaの記事ID。未指定なら最新の記事を使用します。",
    )
    parser.add_argument(
        "--force-upload",
        action="store_true",
        help="当日分が既に投稿済みでもYouTubeアップロードを試行します（テスト用）。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pipeline = build_pipeline_use_case()
    try:
        result = pipeline.execute(
            GenerateDailyVideoInput(
                article_id=args.article_id,
                force_upload=args.force_upload,
            )
        )
    except PipelineError as exc:
        print(exc, file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive fallback
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

    print(f"status: {result.status.status}")
    if result.youtube_video_id:
        print(f"youtube_id: {result.youtube_video_id}")
    if result.video:
        print(f"video_path: {result.video.file_path}")
    if result.metadata and result.metadata.file_path:
        print(f"metadata_path: {result.metadata.file_path}")
    if result.status.notes:
        print("notes:")
        for note in result.status.notes:
            print(f"- {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
