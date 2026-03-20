"""アンケート受信エンドポイントのユニットテスト。

対象: src/python/api/routers/feedback.py
テスト観点: POST /feedback のスコアバリデーション、UNIQUE制約、free_comment任意、キュー登録

Note:
    DB は使用しない。FastAPI TestClient で検証する。
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from src.python.api.main import app
from src.python.domain.schemas.feedback import FeedbackCreateRequest


def _valid_feedback(**overrides: object) -> dict[str, object]:
    """正常なリクエストボディを生成するヘルパー。"""
    base: dict[str, object] = {
        "visit_id": str(uuid.uuid4()),
        "score_consultation": 4,
        "score_information": 3,
        "score_revisit": 5,
    }
    base.update(overrides)
    return base


class TestFeedbackCreateValidation:
    """スキーマバリデーションのテスト。"""

    # AC-01: score 3種が 1〜5 で正常に生成できる
    def test_正常なスコアでインスタンスが生成できる(self) -> None:
        """score 1〜5 で FeedbackCreateRequest が生成できる。"""
        req = FeedbackCreateRequest(
            visit_id=uuid.uuid4(),
            score_consultation=1,
            score_information=5,
            score_revisit=3,
        )
        assert req.score_consultation == 1
        assert req.score_information == 5

    # AC-01: score が 0 の場合はバリデーションエラー
    def test_スコア0はバリデーションエラー(self) -> None:
        """score_consultation=0 で ValidationError。"""
        with pytest.raises(ValidationError):
            FeedbackCreateRequest(
                visit_id=uuid.uuid4(),
                score_consultation=0,
                score_information=3,
                score_revisit=3,
            )

    # AC-01: score が 6 の場合はバリデーションエラー
    def test_スコア6はバリデーションエラー(self) -> None:
        """score_revisit=6 で ValidationError。"""
        with pytest.raises(ValidationError):
            FeedbackCreateRequest(
                visit_id=uuid.uuid4(),
                score_consultation=3,
                score_information=3,
                score_revisit=6,
            )

    # AC-03: free_comment は任意
    def test_free_commentなしで生成できる(self) -> None:
        """free_comment 省略で正常生成。"""
        req = FeedbackCreateRequest(
            visit_id=uuid.uuid4(),
            score_consultation=4,
            score_information=4,
            score_revisit=4,
        )
        assert req.free_comment is None

    # AC-03: free_comment ありで生成できる
    def test_free_commentありで生成できる(self) -> None:
        """free_comment を含むリクエストが正常生成。"""
        req = FeedbackCreateRequest(
            visit_id=uuid.uuid4(),
            score_consultation=4,
            score_information=4,
            score_revisit=4,
            free_comment="接客がとても丁寧でした",
        )
        assert req.free_comment == "接客がとても丁寧でした"


@pytest.mark.asyncio
class TestFeedbackEndpoint:
    """POST /feedback エンドポイントのテスト。"""

    # AC-01: 正常リクエストで 201 が返る
    async def test_正常リクエストで201が返る(self) -> None:
        """score 3種 + visit_id で 201 Created が返る。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/feedback", json=_valid_feedback())
        assert response.status_code == 201
        body = response.json()
        assert "feedback_id" in body
        assert body["score_consultation"] == 4

    # AC-01: 必須フィールド欠落で 422 が返る
    async def test_必須フィールド欠落で422が返る(self) -> None:
        """visit_id なしで 422 Unprocessable Entity。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/feedback",
                json={"score_consultation": 3, "score_information": 3, "score_revisit": 3},
            )
        assert response.status_code == 422

    # AC-03: free_comment 付きで正常応答
    async def test_free_comment付きで正常応答(self) -> None:
        """free_comment を含むリクエストで 201 が返る。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/feedback",
                json=_valid_feedback(free_comment="丁寧な接客でした"),
            )
        assert response.status_code == 201
        body = response.json()
        assert body["free_comment"] == "丁寧な接客でした"

    # AC-04: レスポンスに interpretation_queued が含まれる
    async def test_レスポンスにinterpretation_queuedが含まれる(self) -> None:
        """free_comment ありの場合 interpretation_queued=True。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/feedback",
                json=_valid_feedback(free_comment="テストコメント"),
            )
        body = response.json()
        assert body["interpretation_queued"] is True

    # AC-04: free_comment なしの場合 interpretation_queued=False
    async def test_free_commentなしでinterpretation_queuedがFalse(self) -> None:
        """free_comment 省略時は interpretation_queued=False。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/feedback", json=_valid_feedback())
        body = response.json()
        assert body["interpretation_queued"] is False
