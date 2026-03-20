"""ヘルスチェックエンドポイントのユニットテスト。

対象: src/python/api/main.py
テスト観点: /health エンドポイントの応答確認

Note:
    DB 接続は不要。FastAPI TestClient で検証する。
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.python.api.main import app


@pytest.mark.asyncio
class TestHealthCheck:
    """ヘルスチェックのテスト。"""

    # AC-01 (T-00): docker compose up 後にヘルスチェックが応答する
    async def test_ヘルスチェックが正常応答する(self) -> None:
        """GET /health が 200 で status=ok を返す。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert "environment" in body
        assert "ai_backend" in body
