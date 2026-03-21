"""店舗一覧エンドポイント。

デモ用の GET /stores エンドポイント。
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.python.db.session import get_db
from src.python.domain.models.store import Store

router = APIRouter(tags=["stores"])


@router.get("/stores")
async def list_stores(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    """全店舗一覧を返す。"""
    result = await db.execute(select(Store))
    stores = result.scalars().all()
    return [
        {
            "store_id": str(s.store_id),
            "store_name": s.store_name,
            "area": s.area,
            "format_type": s.format_type,
            "status": s.status,
        }
        for s in stores
    ]
