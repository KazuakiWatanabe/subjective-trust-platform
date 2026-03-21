"""接客タグ入力エンドポイント。

設計書 §5.1 に基づくスタッフ向け接客タグ入力 API。
"""
# TODO(phase2): C# 移管予定 — REST API は ASP.NET Core Minimal API に移行する

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.python.db.session import get_db
from src.python.domain.models.visit import Visit
from src.python.domain.schemas.visit import VisitCreateRequest, VisitResponse

router = APIRouter(tags=["visits"])


@router.post(
    "/visits",
    response_model=VisitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_visit(
    request: VisitCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> VisitResponse:
    """来店記録を作成する。"""
    visit_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    visit = Visit(
        visit_id=visit_id,
        store_id=request.store_id,
        staff_id=request.staff_id,
        customer_id=request.customer_id,
        visit_datetime=now,
        visit_purpose=request.visit_purpose,
        purchase_flag=(request.contact_result == "purchase"),
        contact_result=request.contact_result,
        out_of_stock_flag=(request.contact_result == "out_of_stock_exit"),
        alternative_proposed=request.alternative_proposed,
        backorder_offered=request.backorder_offered,
        anxiety_tags=request.anxiety_tags,
        next_visit_likelihood=request.next_visit_likelihood,
        staff_note=request.staff_note,
    )
    db.add(visit)

    return VisitResponse(
        visit_id=visit_id,
        store_id=request.store_id,
        visit_purpose=request.visit_purpose,
        contact_result=request.contact_result,
        visit_datetime=now,
    )
