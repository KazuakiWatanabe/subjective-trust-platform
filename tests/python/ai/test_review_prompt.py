"""外部レビュー専用プロンプトのユニットテスト。

対象: src/python/ai/prompts/review_interpretation.py
"""

from src.python.ai.prompts.review_interpretation import (
    PROMPT_VERSION,
    build_review_prompt,
)


class TestReviewPrompt:
    """プロンプトテンプレートのテスト。"""

    def test_PROMPT_VERSIONが定義されている(self) -> None:
        assert isinstance(PROMPT_VERSION, str)
        assert len(PROMPT_VERSION) > 0

    def test_プロンプトが生成される(self) -> None:
        prompt = build_review_prompt(
            rating=4,
            review_date="2026-03-20",
            review_text="接客がとても丁寧でした",
        )
        assert "接客がとても丁寧でした" in prompt
        assert "4点" in prompt
        assert "mentions" in prompt

    def test_プロンプトに出力スキーマが含まれる(self) -> None:
        prompt = build_review_prompt(rating=3, review_date="2026-03-20", review_text="テスト")
        assert "trust_dimension" in prompt
        assert "subjective_hints" in prompt
        assert "overall_sentiment" in prompt
        assert "review_type" in prompt
        assert "contains_competitor_mention" in prompt

    def test_空テキストでもプロンプトが生成される(self) -> None:
        prompt = build_review_prompt(rating=1, review_date="2026-03-20", review_text="")
        assert isinstance(prompt, str)
        assert "1点" in prompt
