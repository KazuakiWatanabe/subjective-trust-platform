"""テスト共通設定。

pytest のフィクスチャ・設定を定義する。

Note:
    DB を使うテストは integration マーカーを付けること。
    ユニットテストでは DB 依存を MockSession でオーバーライドする。
"""

import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

# テスト実行時は .env.local を読み込まないようにする
os.environ.setdefault("AI_BACKEND", "mock")
os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://trust_user:trust_pass@db:5432/trust_platform",
)

from src.python.api.main import app  # noqa: E402
from src.python.db.session import get_db  # noqa: E402


class _MockScalarsResult:
    """モック DB の scalars() 結果。空リストを返す。"""

    def all(self) -> list[object]:
        return []


class _MockExecuteResult:
    """モック DB の execute() 結果。"""

    def scalars(self) -> _MockScalarsResult:
        return _MockScalarsResult()


class _MockSession:
    """ユニットテスト用のモック DB セッション。DB 接続なしで動作する。"""

    async def execute(self, *args: object, **kwargs: object) -> _MockExecuteResult:
        return _MockExecuteResult()

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def flush(self) -> None:
        pass

    def add(self, instance: object) -> None:
        pass


async def _override_get_db() -> AsyncGenerator[_MockSession, None]:
    """ユニットテスト用のモック DB セッションを返す。"""
    yield _MockSession()


# FastAPI の DB 依存をオーバーライド（ユニットテストでは DB 不要）
app.dependency_overrides[get_db] = _override_get_db
