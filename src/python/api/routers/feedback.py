"""アンケート受信エンドポイント。

設計書 §5.2 に基づく顧客ミニアンケート受信 API。
"""
# TODO(phase2): C# 移管予定 — REST API は ASP.NET Core Minimal API に移行する

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.python.db.session import get_db
from src.python.domain.models.feedback import Feedback
from src.python.domain.schemas.feedback import FeedbackCreateRequest, FeedbackResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_feedback(
    request: FeedbackCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    """アンケート回答を保存する。"""
    feedback_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    feedback = Feedback(
        feedback_id=feedback_id,
        visit_id=request.visit_id,
        score_consultation=request.score_consultation,
        score_information=request.score_information,
        score_revisit=request.score_revisit,
        free_comment=request.free_comment,
        submitted_at=now,
    )
    db.add(feedback)

    interpretation_queued = bool(request.free_comment and request.free_comment.strip())
    if interpretation_queued:
        logger.info(
            "AI 解釈キュー登録: feedback_id=%s, visit_id=%s",
            feedback_id,
            request.visit_id,
        )

    return FeedbackResponse(
        feedback_id=feedback_id,
        visit_id=request.visit_id,
        score_consultation=request.score_consultation,
        score_information=request.score_information,
        score_revisit=request.score_revisit,
        free_comment=request.free_comment,
        submitted_at=now,
        interpretation_queued=interpretation_queued,
    )
