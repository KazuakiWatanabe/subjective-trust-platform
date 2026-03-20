"""アンケート受信エンドポイント。

設計書 §5.2 に基づく顧客ミニアンケート受信 API。
score_consultation / score_information / score_revisit（1〜5）と任意の free_comment を受け付ける。

Note:
    1 来店に対して Feedback は 1 件のみ（DB の UNIQUE 制約で担保）。
    free_comment が存在する場合は AI 解釈パイプラインへのキュー登録を行う。
"""
# TODO(phase2): C# 移管予定 — REST API は ASP.NET Core Minimal API に移行する

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, status

from src.python.domain.schemas.feedback import FeedbackCreateRequest, FeedbackResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_feedback(request: FeedbackCreateRequest) -> FeedbackResponse:
    """アンケート回答を保存する。

    Args:
        request: アンケート回答リクエスト

    Returns:
        FeedbackResponse: 保存結果と解釈キュー登録状態

    Note:
        Phase 1 では DB 書き込みなし。統合テストで DB 連携を確認する。
        UNIQUE 制約（1 来店 1 回答）は DB レベルで担保する。
    """
    feedback_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # free_comment がある場合は AI 解釈パイプラインへキュー登録
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
