"""接客タグ入力エンドポイント。

設計書 §5.1 に基づくスタッフ向け接客タグ入力 API。
来店目的・接客結果を必須とし、条件に応じて代替提案フラグ・不安点タグを受け付ける。

Note:
    Phase 1 では DB 書き込みは行わず、インメモリでレスポンスを返す。
    DB 統合は統合テストで確認する。
"""
# TODO(phase2): C# 移管予定 — REST API は ASP.NET Core Minimal API に移行する

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, status

from src.python.domain.schemas.visit import VisitCreateRequest, VisitResponse

router = APIRouter(tags=["visits"])


@router.post(
    "/visits",
    response_model=VisitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_visit(request: VisitCreateRequest) -> VisitResponse:
    """来店記録を作成する。

    Args:
        request: 接客タグ入力リクエスト

    Returns:
        VisitResponse: 作成された来店記録の概要

    Note:
        Phase 1 では DB 書き込みなし。統合テストで DB 連携を確認する。
    """
    visit_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Phase 1: DB 書き込みは統合テストで確認。ここではレスポンスのみ返す
    return VisitResponse(
        visit_id=visit_id,
        store_id=request.store_id,
        visit_purpose=request.visit_purpose,
        contact_result=request.contact_result,
        visit_datetime=now,
    )
