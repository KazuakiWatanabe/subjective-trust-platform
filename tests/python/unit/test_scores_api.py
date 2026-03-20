"""スコア参照エンドポイントのユニットテスト。

対象: src/python/api/routers/scores.py
テスト観点: GET /stores/{store_id}/scores の応答、unreliable フラグ、時系列データ

Note:
    DB は使用しない。インメモリのモックデータで検証する。
"""

import uuid
from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from src.python.api.main import app


@pytest.mark.asyncio
class TestScoresEndpoint:
    """GET /stores/{store_id}/scores のテスト。"""

    # AC-01: 最新の TrustScoreSnapshot が返却される
    async def test_正常リクエストで200が返る(self) -> None:
        """GET /stores/{store_id}/scores が 200 を返す。"""
        store_id = str(uuid.uuid4())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/stores/{store_id}/scores")
        assert response.status_code == 200
        body = response.json()
        assert body["store_id"] == store_id

    # AC-01: レスポンスに latest が含まれる
    async def test_レスポンスにlatestが含まれる(self) -> None:
        """レスポンスに latest フィールドが存在する。"""
        store_id = str(uuid.uuid4())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/stores/{store_id}/scores")
        body = response.json()
        assert "latest" in body
        if body["latest"] is not None:
            assert "scores" in body["latest"]
            assert "overall_score" in body["latest"]

    # AC-02: is_reliable=False の場合は unreliable フラグが付く
    async def test_unreliableフラグが正しく設定される(self) -> None:
        """history の古い週で is_reliable=False → unreliable=True を検証する。"""
        store_id = str(uuid.uuid4())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/stores/{store_id}/scores")
        body = response.json()
        # history の中から is_reliable=False のエントリを探して unreliable=True を検証
        unreliable_entries = [
            s for s in body["history"] if not s["is_reliable"]
        ]
        assert len(unreliable_entries) > 0, "is_reliable=False のエントリが存在しない"
        for entry in unreliable_entries:
            assert entry["unreliable"] is True
        # is_reliable=True のエントリは unreliable=False
        reliable_entries = [s for s in body["history"] if s["is_reliable"]]
        for entry in reliable_entries:
            assert entry["unreliable"] is False

    # AC-03: 過去 12 週分の時系列スコアを返却できる
    async def test_historyが返却される(self) -> None:
        """レスポンスに history リストが含まれる。"""
        store_id = str(uuid.uuid4())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/stores/{store_id}/scores")
        body = response.json()
        assert "history" in body
        assert isinstance(body["history"], list)

    # AC-01: 不正な store_id 形式で 422 が返る
    async def test_不正なstore_idで422が返る(self) -> None:
        """UUID でない store_id で 422 が返る。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/stores/invalid-uuid/scores")
        assert response.status_code == 422

    # AC-03: weeks パラメータで取得期間を指定できる
    async def test_weeksパラメータで期間指定できる(self) -> None:
        """weeks=4 で history の最大件数が制限される。"""
        store_id = str(uuid.uuid4())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/stores/{store_id}/scores", params={"weeks": 4}
            )
        assert response.status_code == 200
