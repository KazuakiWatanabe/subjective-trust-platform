"""スコア参照エンドポイントのユニットテスト。

対象: src/python/api/routers/scores.py
テスト観点: GET /stores/{store_id}/scores の応答、unreliable フラグ、時系列データ

Note:
    DB はモックでオーバーライドされている（conftest.py）。
    DB にデータがない場合は latest=None, history=[] が返る。
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from src.python.api.main import app


@pytest.mark.asyncio
class TestScoresEndpoint:
    """GET /stores/{store_id}/scores のテスト。"""

    # AC-01: 正常リクエストで 200 が返る
    async def test_正常リクエストで200が返る(self) -> None:
        """GET /stores/{store_id}/scores が 200 を返す。"""
        store_id = str(uuid.uuid4())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/stores/{store_id}/scores")
        assert response.status_code == 200
        body = response.json()
        assert body["store_id"] == store_id

    # AC-01: レスポンスに latest と history が含まれる
    async def test_レスポンスにlatestとhistoryが含まれる(self) -> None:
        """レスポンスに latest, history フィールドが存在する。"""
        store_id = str(uuid.uuid4())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/stores/{store_id}/scores")
        body = response.json()
        assert "latest" in body
        assert "history" in body
        assert isinstance(body["history"], list)

    # AC-01: DB にデータがなければ latest=None, history=[]
    async def test_データなしでlatest_null_history空(self) -> None:
        """モック DB はデータを返さないため latest=None, history=[]。"""
        store_id = str(uuid.uuid4())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/stores/{store_id}/scores")
        body = response.json()
        assert body["latest"] is None
        assert body["history"] == []

    # AC-01: 不正な store_id 形式で 422 が返る
    async def test_不正なstore_idで422が返る(self) -> None:
        """UUID でない store_id で 422 が返る。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/stores/invalid-uuid/scores")
        assert response.status_code == 422

    # AC-03: weeks パラメータが受け付けられる
    async def test_weeksパラメータで期間指定できる(self) -> None:
        """weeks=4 が正常に受け付けられる。"""
        store_id = str(uuid.uuid4())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/stores/{store_id}/scores", params={"weeks": 4}
            )
        assert response.status_code == 200
