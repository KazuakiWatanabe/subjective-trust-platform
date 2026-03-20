"""接客タグ入力エンドポイントのユニットテスト。

対象: src/python/api/routers/visits.py
テスト観点: POST /visits の入力バリデーション、条件付きフィールド、レスポンス

Note:
    DB は使用しない。FastAPI TestClient で検証する。
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from src.python.api.main import app
from src.python.domain.schemas.visit import VisitCreateRequest


def _valid_request(**overrides: object) -> dict[str, object]:
    """正常なリクエストボディを生成するヘルパー。"""
    base = {
        "store_id": str(uuid.uuid4()),
        "visit_purpose": "purchase",
        "contact_result": "purchase",
    }
    base.update(overrides)
    return base


class TestVisitCreateValidation:
    """スキーマバリデーションのテスト。"""

    # AC-01: 来店目的・接客結果の必須入力でレコードが作成される
    def test_正常なリクエストがバリデーションを通過する(self) -> None:
        """必須フィールドのみで VisitCreateRequest が生成できる。"""
        req = VisitCreateRequest(
            store_id=uuid.uuid4(),
            visit_purpose="purchase",
            contact_result="purchase",
        )
        assert req.visit_purpose == "purchase"
        assert req.contact_result == "purchase"

    # AC-01: 不正な visit_purpose は拒否される
    def test_不正なvisit_purposeはバリデーションエラー(self) -> None:
        """visit_purpose に未知の値を指定するとエラーになる。"""
        with pytest.raises(ValidationError):
            VisitCreateRequest(
                store_id=uuid.uuid4(),
                visit_purpose="unknown",  # type: ignore[arg-type]
                contact_result="purchase",
            )

    # AC-02: 欠品離脱の場合のみ alternative_proposed を受け付ける
    def test_欠品離脱でalternative_proposedが受け付けられる(self) -> None:
        """out_of_stock_exit 時に alternative_proposed=False が有効。"""
        req = VisitCreateRequest(
            store_id=uuid.uuid4(),
            visit_purpose="purchase",
            contact_result="out_of_stock_exit",
            alternative_proposed=False,
        )
        assert req.alternative_proposed is False

    # AC-02: 欠品離脱以外で alternative_proposed はエラー
    def test_欠品離脱以外でalternative_proposedはエラー(self) -> None:
        """purchase 時に alternative_proposed を指定するとエラー。"""
        with pytest.raises(ValidationError, match="alternative_proposed"):
            VisitCreateRequest(
                store_id=uuid.uuid4(),
                visit_purpose="purchase",
                contact_result="purchase",
                alternative_proposed=True,
            )

    # AC-03: 離脱の場合のみ不安点タグを受け付ける
    def test_離脱でanxiety_tagsが受け付けられる(self) -> None:
        """exit 時に anxiety_tags が有効。"""
        req = VisitCreateRequest(
            store_id=uuid.uuid4(),
            visit_purpose="comparison",
            contact_result="exit",
            anxiety_tags=["price", "size_spec"],
        )
        assert req.anxiety_tags == ["price", "size_spec"]

    # AC-03: 離脱以外で anxiety_tags はエラー
    def test_離脱以外でanxiety_tagsはエラー(self) -> None:
        """purchase 時に anxiety_tags を指定するとエラー。"""
        with pytest.raises(ValidationError, match="anxiety_tags"):
            VisitCreateRequest(
                store_id=uuid.uuid4(),
                visit_purpose="purchase",
                contact_result="purchase",
                anxiety_tags=["price"],
            )


@pytest.mark.asyncio
class TestVisitsEndpoint:
    """POST /visits エンドポイントのテスト。"""

    # AC-01: POST /visits で正常にレコードが作成される
    async def test_正常リクエストで201が返る(self) -> None:
        """必須フィールドのみで 201 Created が返る。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/visits", json=_valid_request())
        assert response.status_code == 201
        body = response.json()
        assert "visit_id" in body
        assert body["visit_purpose"] == "purchase"

    # AC-01: 必須フィールド欠落で 422 が返る
    async def test_必須フィールド欠落で422が返る(self) -> None:
        """store_id なしで 422 Unprocessable Entity が返る。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/visits", json={"visit_purpose": "purchase"})
        assert response.status_code == 422

    # AC-02: 欠品離脱 + alternative_proposed で正常応答
    async def test_欠品離脱でalternative_proposedが正常応答(self) -> None:
        """out_of_stock_exit + alternative_proposed=false で 201 が返る。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/visits",
                json=_valid_request(
                    contact_result="out_of_stock_exit",
                    alternative_proposed=False,
                ),
            )
        assert response.status_code == 201

    # AC-03: 離脱 + anxiety_tags で正常応答
    async def test_離脱でanxiety_tagsが正常応答(self) -> None:
        """exit + anxiety_tags で 201 が返る。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/visits",
                json=_valid_request(
                    visit_purpose="comparison",
                    contact_result="exit",
                    anxiety_tags=["price", "competitor"],
                ),
            )
        assert response.status_code == 201
