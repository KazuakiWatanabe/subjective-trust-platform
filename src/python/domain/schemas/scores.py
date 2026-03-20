"""スコア参照 API スキーマ。

設計書 §6.1 に基づくスコア参照のレスポンスモデル。

Note:
    is_reliable=False の場合は unreliable フラグを付与する。
    過去 12 週分の時系列データを返却可能。
"""
# TODO(phase2): C# 移管予定 — REST API は ASP.NET Core Minimal API に移行する

import uuid
from datetime import date

from pydantic import BaseModel


class DimensionScores(BaseModel):
    """5 次元スコア。"""

    product: float
    service: float
    proposal: float
    operation: float
    story: float


class ScoreSnapshotResponse(BaseModel):
    """スコアスナップショット 1 件分。"""

    snapshot_date: date
    scores: DimensionScores
    overall_score: float
    event_count: int
    is_reliable: bool
    unreliable: bool


class StoreScoresResponse(BaseModel):
    """GET /stores/{store_id}/scores レスポンスボディ。"""

    store_id: uuid.UUID
    latest: ScoreSnapshotResponse | None
    history: list[ScoreSnapshotResponse]
