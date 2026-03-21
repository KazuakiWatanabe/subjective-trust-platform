"""スコア参照エンドポイント。

設計書 §6.1 に基づく店舗信頼スコア参照 API。
"""
# TODO(phase2): C# 移管予定 — REST API は ASP.NET Core Minimal API に移行する

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.python.db.session import get_db
from src.python.domain.models.trust_score_snapshot import TrustScoreSnapshot
from src.python.domain.schemas.scores import (
    DimensionScores,
    ScoreSnapshotResponse,
    StoreScoresResponse,
)

router = APIRouter(tags=["scores"])


def _snapshot_to_response(s: TrustScoreSnapshot) -> ScoreSnapshotResponse:
    """DB モデルをレスポンススキーマに変換する。"""
    is_reliable = s.is_reliable
    return ScoreSnapshotResponse(
        snapshot_date=s.snapshot_date,
        scores=DimensionScores(
            product=float(s.product_score or 50),
            service=float(s.service_score or 50),
            proposal=float(s.proposal_score or 50),
            operation=float(s.operation_score or 50),
            story=float(s.story_score or 50),
        ),
        overall_score=float(s.overall_score or 50),
        event_count=s.event_count or 0,
        is_reliable=is_reliable,
        unreliable=not is_reliable,
    )


@router.get(
    "/stores/{store_id}/scores",
    response_model=StoreScoresResponse,
)
async def get_store_scores(
    store_id: uuid.UUID,
    weeks: int = Query(default=12, ge=1, le=52),
    db: AsyncSession = Depends(get_db),
) -> StoreScoresResponse:
    """店舗の信頼スコアを取得する。"""
    cutoff = date.today() - timedelta(weeks=weeks)
    stmt = (
        select(TrustScoreSnapshot)
        .where(
            TrustScoreSnapshot.target_type == "store",
            TrustScoreSnapshot.target_id == store_id,
            TrustScoreSnapshot.snapshot_date >= cutoff,
        )
        .order_by(TrustScoreSnapshot.snapshot_date.desc())
    )
    result = await db.execute(stmt)
    snapshots = result.scalars().all()

    history = [_snapshot_to_response(s) for s in snapshots]
    latest = history[0] if history else None

    return StoreScoresResponse(
        store_id=store_id,
        latest=latest,
        history=history,
    )
