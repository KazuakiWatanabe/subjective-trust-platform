"""フィードバック（Feedback）API スキーマ。

設計書 §5.2 に基づく顧客ミニアンケート受信のリクエスト・レスポンスモデル。

Note:
    score_consultation / score_information / score_revisit は 1〜5 の 5 段階。
    1 来店に対して Feedback は 1 件のみ（visit_id に UNIQUE 制約）。
    free_comment は任意。AI 解釈パイプラインの主要入力となる。
"""
# TODO(phase2): C# 移管予定 — REST API は ASP.NET Core Minimal API に移行する

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FeedbackCreateRequest(BaseModel):
    """POST /feedback リクエストボディ。

    Args:
        visit_id: 来店 ID（必須、1 来店 1 回答）
        score_consultation: 安心して相談できたか（1〜5）
        score_information: 欲しい情報を得られたか（1〜5）
        score_revisit: また相談したいか（1〜5）
        free_comment: 自由記述（任意）
    """

    visit_id: uuid.UUID
    score_consultation: int = Field(ge=1, le=5)
    score_information: int = Field(ge=1, le=5)
    score_revisit: int = Field(ge=1, le=5)
    free_comment: str | None = None


class FeedbackResponse(BaseModel):
    """POST /feedback レスポンスボディ。"""

    feedback_id: uuid.UUID
    visit_id: uuid.UUID
    score_consultation: int
    score_information: int
    score_revisit: int
    free_comment: str | None
    submitted_at: datetime
    interpretation_queued: bool
    message: str = "アンケート回答が保存されました"
