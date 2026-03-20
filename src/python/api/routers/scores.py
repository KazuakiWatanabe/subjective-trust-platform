"""スコア参照エンドポイント。

設計書 §6.1 に基づく店舗信頼スコア参照 API。
最新スナップショットと過去 12 週分の時系列データを返す。

Note:
    Phase 1 では DB からの取得ではなくモックデータを返す。
    DB 統合は統合テストで確認する。
    is_reliable=False の場合は unreliable=True を付与する。
"""
# TODO(phase2): C# 移管予定 — REST API は ASP.NET Core Minimal API に移行する

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Query

from src.python.domain.schemas.scores import (
    DimensionScores,
    ScoreSnapshotResponse,
    StoreScoresResponse,
)
from src.python.scoring.calculator import BASE_SCORE

router = APIRouter(tags=["scores"])


def _generate_mock_snapshot(snapshot_date: date, weeks_ago: int) -> ScoreSnapshotResponse:
    """モックスナップショットを生成する。

    Args:
        snapshot_date: スナップショット日付
        weeks_ago: 何週前のデータか（古いほど base_score に近づく）

    Returns:
        ScoreSnapshotResponse
    """
    # 古いデータほど base_score に近い値を返す
    base = BASE_SCORE
    event_count = max(5, 25 - weeks_ago * 2)
    is_reliable = event_count >= 20

    scores = DimensionScores(
        product=round(base + 3.0 - weeks_ago * 0.2, 2),
        service=round(base + 5.0 - weeks_ago * 0.3, 2),
        proposal=round(base + 1.0 - weeks_ago * 0.1, 2),
        operation=round(base + 2.0 - weeks_ago * 0.15, 2),
        story=round(base + 4.0 - weeks_ago * 0.25, 2),
    )
    overall = round(
        (scores.product + scores.service + scores.proposal
         + scores.operation + scores.story) / 5,
        2,
    )

    return ScoreSnapshotResponse(
        snapshot_date=snapshot_date,
        scores=scores,
        overall_score=overall,
        event_count=event_count,
        is_reliable=is_reliable,
        unreliable=not is_reliable,
    )


@router.get(
    "/stores/{store_id}/scores",
    response_model=StoreScoresResponse,
)
async def get_store_scores(
    store_id: uuid.UUID,
    weeks: int = Query(default=12, ge=1, le=52, description="取得する週数（1〜52）"),
) -> StoreScoresResponse:
    """店舗の信頼スコアを取得する。

    Args:
        store_id: 店舗 ID
        weeks: 取得する過去の週数（デフォルト 12）

    Returns:
        StoreScoresResponse: 最新スナップショットと時系列データ

    Note:
        Phase 1 ではモックデータを返す。DB 統合は統合テストで確認する。
    """
    today = date.today()
    history: list[ScoreSnapshotResponse] = []

    for i in range(weeks):
        snapshot_date = today - timedelta(weeks=i)
        snapshot = _generate_mock_snapshot(snapshot_date, weeks_ago=i)
        history.append(snapshot)

    latest = history[0] if history else None

    return StoreScoresResponse(
        store_id=store_id,
        latest=latest,
        history=history,
    )
