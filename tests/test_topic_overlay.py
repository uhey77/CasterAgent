from __future__ import annotations

from daily2video.infrastructure.services.topic_overlay import _extract_research_items


def test_extract_research_items_prefers_script_titles_when_available() -> None:
    script_text = """
    本日は11項目をご紹介します。
    それでは一つ目の「Alpha」について詳しく見ていきましょう。
    続いて二つ目の「Beta」について見ていきます。
    """
    article_text = """
    # セクション
    #### 1) Alpha
    #### 2) Beta
    #### 3) Gamma
    """

    items = _extract_research_items(script_text, article_text)
    titles = [title for _, title in items]

    assert titles == ["Alpha", "Beta"]


def test_extract_research_items_falls_back_to_article_when_script_empty() -> None:
    script_text = ""
    article_text = """
    # セクション
    #### 1) Alpha
    #### 2) Beta
    """

    items = _extract_research_items(script_text, article_text)
    titles = [title for _, title in items]

    assert titles == ["Alpha", "Beta"]


def test_extract_research_items_supports_bracket_titles() -> None:
    script_text = """
    まずは【Alpha】について見ていきましょう。
    続いて、【Beta】の研究です。
    最後に、【Gamma】を紹介します。
    """
    article_text = None

    items = _extract_research_items(script_text, article_text)
    titles = [title for _, title in items]

    assert titles == ["Alpha", "Beta", "Gamma"]
