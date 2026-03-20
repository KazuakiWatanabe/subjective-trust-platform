"""AI 解釈パイプラインのユニットテスト。

対象: src/python/interpretation/pipeline.py
テスト観点: Feedback/ReviewExternal からの解釈実行、TrustEvent 生成、
            PII マスキング、confidence による needs_review 判定

Note:
    DB・AI API はモックを使用。実際の API 呼び出しは行わない。
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.python.interpretation.pipeline import (
    InterpretationPipeline,
    mask_pii,
)
from src.python.interpretation.schemas import (
    SubjectiveHints,
    TrustInterpretation,
)


def _make_interpretation(
    confidence: float = 0.85,
    dimension: str = "service",
    sentiment: str = "positive",
) -> TrustInterpretation:
    """テスト用 TrustInterpretation を生成するヘルパー。"""
    return TrustInterpretation(
        trust_dimension=dimension,  # type: ignore[arg-type]
        sentiment=sentiment,  # type: ignore[arg-type]
        severity=1,
        theme_tags=["テスト"],
        summary="テスト要約",
        interpretation="テスト解釈",
        subjective_hints=SubjectiveHints(
            trait_signal="テスト trait",
            state_signal=None,
            meta_signal=None,
        ),
        confidence=confidence,
    )


class TestMaskPii:
    """AC-05: 個人識別情報が Claude API / Bedrock に送信されない。"""

    # AC-05: 電話番号がマスキングされる
    def test_電話番号がマスキングされる(self) -> None:
        """電話番号パターンが [PHONE] に置換される。"""
        text = "連絡先は 090-1234-5678 です"
        result = mask_pii(text)
        assert "090-1234-5678" not in result
        assert "[PHONE]" in result

    # AC-05: メールアドレスがマスキングされる
    def test_メールアドレスがマスキングされる(self) -> None:
        """メールアドレスパターンが [EMAIL] に置換される。"""
        text = "メールは taro@example.com まで"
        result = mask_pii(text)
        assert "taro@example.com" not in result
        assert "[EMAIL]" in result

    # AC-05: 氏名パターンがマスキングされる
    def test_マスキング後もテキスト本体は残る(self) -> None:
        """PII 以外のテキストが保持される。"""
        text = "接客がとても丁寧でした。連絡先は 03-1234-5678 です。"
        result = mask_pii(text)
        assert "接客がとても丁寧でした" in result
        assert "03-1234-5678" not in result


class TestInterpretationPipeline:
    """パイプライン本体のテスト。"""

    def _make_pipeline(
        self,
        mock_client: AsyncMock | None = None,
    ) -> InterpretationPipeline:
        """テスト用パイプラインインスタンスを生成する。"""
        client = mock_client or AsyncMock()
        if mock_client is None:
            client.interpret = AsyncMock(return_value=_make_interpretation())
        return InterpretationPipeline(client=client)

    # AC-01: Feedback.free_comment を対象に実行される
    @pytest.mark.asyncio
    async def test_Feedbackのfree_commentが解釈対象になる(self) -> None:
        """process_feedback が free_comment を client.interpret に渡す。"""
        mock_client = AsyncMock()
        mock_client.interpret = AsyncMock(return_value=_make_interpretation())
        pipeline = self._make_pipeline(mock_client)

        store_id = uuid.uuid4()
        feedback_id = uuid.uuid4()
        events = await pipeline.process_feedback(
            feedback_id=feedback_id,
            store_id=store_id,
            free_comment="接客がとても丁寧でした",
        )

        mock_client.interpret.assert_called_once()
        call_text = mock_client.interpret.call_args[0][0]
        assert "接客がとても丁寧でした" in call_text
        assert len(events) == 1

    # AC-01: ReviewExternal のテキストが解釈対象になる
    @pytest.mark.asyncio
    async def test_ReviewExternalのテキストが解釈対象になる(self) -> None:
        """process_review が review_text を client.interpret に渡す。"""
        mock_client = AsyncMock()
        mock_client.interpret = AsyncMock(return_value=_make_interpretation())
        pipeline = self._make_pipeline(mock_client)

        store_id = uuid.uuid4()
        review_id = uuid.uuid4()
        events = await pipeline.process_review(
            review_id=review_id,
            store_id=store_id,
            review_text="品質が期待以下でした",
        )

        mock_client.interpret.assert_called_once()
        assert len(events) == 1

    # AC-02: AI 解釈結果が TrustEvent 辞書として生成される
    @pytest.mark.asyncio
    async def test_解釈結果がTrustEvent辞書として生成される(self) -> None:
        """process_feedback が TrustEvent 相当の辞書を返す。"""
        interp = _make_interpretation(confidence=0.85, dimension="service", sentiment="positive")
        mock_client = AsyncMock()
        mock_client.interpret = AsyncMock(return_value=interp)
        pipeline = self._make_pipeline(mock_client)

        store_id = uuid.uuid4()
        feedback_id = uuid.uuid4()
        events = await pipeline.process_feedback(
            feedback_id=feedback_id,
            store_id=store_id,
            free_comment="良い接客でした",
        )

        event = events[0]
        assert event["trust_dimension"] == "service"
        assert event["sentiment"] == "positive"
        assert event["source_type"] == "feedback"
        assert event["source_id"] == feedback_id
        assert event["store_id"] == store_id

    # AC-03: confidence < 0.6 の TrustEvent には needs_review = True
    @pytest.mark.asyncio
    async def test_低confidenceでneeds_reviewがTrue(self) -> None:
        """confidence < 0.6 の解釈結果で needs_review=True が設定される。"""
        interp = _make_interpretation(confidence=0.55)
        mock_client = AsyncMock()
        mock_client.interpret = AsyncMock(return_value=interp)
        pipeline = self._make_pipeline(mock_client)

        events = await pipeline.process_feedback(
            feedback_id=uuid.uuid4(),
            store_id=uuid.uuid4(),
            free_comment="微妙でした",
        )

        assert events[0]["needs_review"] is True

    # AC-03: confidence >= 0.6 の TrustEvent には needs_review = False
    @pytest.mark.asyncio
    async def test_高confidenceでneeds_reviewがFalse(self) -> None:
        """confidence >= 0.6 の解釈結果で needs_review=False が設定される。"""
        interp = _make_interpretation(confidence=0.85)
        mock_client = AsyncMock()
        mock_client.interpret = AsyncMock(return_value=interp)
        pipeline = self._make_pipeline(mock_client)

        events = await pipeline.process_feedback(
            feedback_id=uuid.uuid4(),
            store_id=uuid.uuid4(),
            free_comment="良い接客でした",
        )

        assert events[0]["needs_review"] is False

    # AC-04: generated_by = 'ai' が TrustEvent に記録される
    @pytest.mark.asyncio
    async def test_generated_byがaiに設定される(self) -> None:
        """AI 解釈による TrustEvent に generated_by='ai' が記録される。"""
        mock_client = AsyncMock()
        mock_client.interpret = AsyncMock(return_value=_make_interpretation())
        pipeline = self._make_pipeline(mock_client)

        events = await pipeline.process_feedback(
            feedback_id=uuid.uuid4(),
            store_id=uuid.uuid4(),
            free_comment="テスト",
        )

        assert events[0]["generated_by"] == "ai"

    # AC-05: PII マスキングされたテキストが AI に渡される
    @pytest.mark.asyncio
    async def test_PIIマスキング後のテキストがAIに渡される(self) -> None:
        """電話番号を含むテキストがマスキングされて interpret に渡される。"""
        mock_client = AsyncMock()
        mock_client.interpret = AsyncMock(return_value=_make_interpretation())
        pipeline = self._make_pipeline(mock_client)

        await pipeline.process_feedback(
            feedback_id=uuid.uuid4(),
            store_id=uuid.uuid4(),
            free_comment="電話は 090-1111-2222 です。接客は良かった。",
        )

        call_text = mock_client.interpret.call_args[0][0]
        assert "090-1111-2222" not in call_text
        assert "接客は良かった" in call_text

    # AC-01: free_comment が None/空の場合はスキップ
    @pytest.mark.asyncio
    async def test_空コメントはスキップされる(self) -> None:
        """free_comment が None や空文字の場合は解釈をスキップする。"""
        mock_client = AsyncMock()
        mock_client.interpret = AsyncMock(return_value=_make_interpretation())
        pipeline = self._make_pipeline(mock_client)

        events = await pipeline.process_feedback(
            feedback_id=uuid.uuid4(),
            store_id=uuid.uuid4(),
            free_comment=None,
        )

        mock_client.interpret.assert_not_called()
        assert len(events) == 0
