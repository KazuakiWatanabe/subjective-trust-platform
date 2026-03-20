"""FastAPI アプリケーションエントリポイント。

ヘルスチェック・ルーター登録・ライフサイクル管理を行う。
"""
# TODO(phase2): C# 移管予定 — REST API は ASP.NET Core Minimal API に移行する

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from src.python.config import get_settings
from src.python.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """アプリケーション起動・終了時の処理。"""
    yield
    await engine.dispose()


app = FastAPI(
    title="Subjective Trust Platform API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """ヘルスチェックエンドポイント。コンテナ・LB からの死活監視用。"""
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.environment,
        "ai_backend": settings.ai_backend,
    }
