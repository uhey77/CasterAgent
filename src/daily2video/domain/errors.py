from __future__ import annotations


class PipelineError(RuntimeError):
    """パイプラインの特定ステップが業務上成立しなかったことを表す。"""

    def __init__(self, step: str, message: str) -> None:
        super().__init__(f"Pipeline step '{step}' failed: {message}")
        self.step = step
        self.message = message


class ArticleNotFoundError(PipelineError):
    """動画化の対象となる記事が存在しない。"""

    def __init__(self) -> None:
        super().__init__("article", "対象の記事が見つかりませんでした")
