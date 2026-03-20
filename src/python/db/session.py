"""SQLAlchemy 非同期セッション管理モジュール。

AsyncSession を提供し、FastAPI の Depends で DI する。

Note:
    Phase 1 では Python で DB セッションを管理する。
"""
# TODO(phase2): C# 移管予定 — DB セッション管理は EF Core に移行する

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.python.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=(settings.environment == "local"),
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends 用の非同期セッションジェネレータ。"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
