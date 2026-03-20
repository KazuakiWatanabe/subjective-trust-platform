"""信頼スコア算出ロジック。

設計書 §2.4 に基づく次元別スコア算出と TrustScoreSnapshot 生成。

算出式:
    dimension_score = base_score
      + Σ(positive_event_weight × recency_decay)
      - Σ(negative_event_weight × severity × recency_decay)

入力: TrustEvent リスト（辞書形式）
出力: TrustScoreSnapshot 相当の辞書
制約:
    - base_score = 50、スコア範囲は 0〜100
    - event_count < 20 → is_reliable = False
    - recency_decay は weights.py の 4 段階を使用

Note:
    Phase 1 では Python で実装。Phase 2 で C# ドメインサービスに移行予定。
"""
# TODO(phase2): C# 移管予定 — スコア算出サービスは C# ドメインサービスに移行する

import math
import uuid
from datetime import date, datetime, timezone
from typing import Any

from src.python.scoring.weights import (
    DIMENSION_WEIGHTS,
    OVERALL_DIMENSION_WEIGHTS,
    get_recency_decay,
)

BASE_SCORE: float = 50.0
_RELIABLE_EVENT_THRESHOLD: int = 20
_ALL_DIMENSIONS: list[str] = ["product", "service", "proposal", "operation", "story"]

# デフォルトの重みマッピング（event_type が不明な場合のフォールバック）
_DEFAULT_WEIGHT: float = 1.0


def _weeks_between(event_date: datetime, reference_date: date) -> int:
    """イベント日時から参照日までの経過週数を返す。

    Args:
        event_date: イベントの detected_at
        reference_date: スナップショットの基準日

    Returns:
        経過週数（1 以上）
    """
    ref_dt = datetime.combine(reference_date, datetime.min.time(), tzinfo=timezone.utc)
    delta = ref_dt - event_date
    weeks = max(1, math.ceil(delta.days / 7))
    return weeks


def _find_event_weight(dimension: str, sentiment: str) -> float:
    """次元・sentiment に対応するデフォルトの基本重みを返す。

    Args:
        dimension: 信頼の 5 次元
        sentiment: positive / negative / neutral

    Returns:
        基本重み（float）
    """
    weights = DIMENSION_WEIGHTS.get(dimension, [])
    # sentiment に対応する重みの平均を返す（大まかなフォールバック）
    matched = [w.base_weight for w in weights if w.direction == sentiment]
    if matched:
        return sum(matched) / len(matched)
    return _DEFAULT_WEIGHT


def calculate_dimension_score(
    dimension: str,
    events: list[dict[str, Any]],
    reference_date: date | None = None,
) -> float:
    """指定次元の信頼スコアを算出する。

    Args:
        dimension: 信頼の 5 次元のいずれか
        events: 当該次元に紐づく TrustEvent 辞書のリスト
        reference_date: 算出基準日（None の場合は今日）

    Returns:
        0.0〜100.0 の次元スコア
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc).date()

    score = BASE_SCORE

    for event in events:
        sentiment = event.get("sentiment", "neutral")
        if sentiment == "neutral":
            continue

        severity = event.get("severity", 1) or 1
        detected_at = event["detected_at"]
        weeks_ago = _weeks_between(detected_at, reference_date)
        decay = get_recency_decay(weeks_ago)
        weight = _find_event_weight(dimension, sentiment)

        if sentiment == "positive":
            score += weight * decay
        elif sentiment == "negative":
            score -= weight * severity * decay

    # スコアを 0〜100 にクランプ
    return max(0.0, min(100.0, score))


class TrustScoreCalculator:
    """信頼スコア算出器。

    TrustEvent リストから 5 次元のスコアを算出し、
    TrustScoreSnapshot 相当の辞書を生成する。
    """

    def calculate_snapshot(
        self,
        store_id: uuid.UUID,
        events: list[dict[str, Any]],
        snapshot_date: date,
    ) -> dict[str, Any]:
        """週次スナップショットを算出する。

        Args:
            store_id: 店舗 ID
            events: 全次元の TrustEvent 辞書リスト
            snapshot_date: スナップショット日付

        Returns:
            TrustScoreSnapshot テーブルに挿入可能な辞書
        """
        # 次元ごとにイベントを分類
        events_by_dim: dict[str, list[dict[str, Any]]] = {
            dim: [] for dim in _ALL_DIMENSIONS
        }
        for event in events:
            dim = event.get("trust_dimension", "")
            if dim in events_by_dim:
                events_by_dim[dim].append(event)

        # 各次元のスコアを算出
        scores: dict[str, float] = {}
        for dim in _ALL_DIMENSIONS:
            scores[dim] = calculate_dimension_score(
                dim, events_by_dim[dim], snapshot_date
            )

        # 総合スコア（加重平均）
        overall = sum(
            scores[dim] * OVERALL_DIMENSION_WEIGHTS.get(dim, 0.2)
            for dim in _ALL_DIMENSIONS
        )

        # is_reliable 判定
        total_event_count = len(events)
        is_reliable = total_event_count >= _RELIABLE_EVENT_THRESHOLD

        return {
            "snapshot_id": uuid.uuid4(),
            "target_type": "store",
            "target_id": store_id,
            "snapshot_date": snapshot_date,
            "product_score": round(scores["product"], 2),
            "service_score": round(scores["service"], 2),
            "proposal_score": round(scores["proposal"], 2),
            "operation_score": round(scores["operation"], 2),
            "story_score": round(scores["story"], 2),
            "overall_score": round(overall, 2),
            "event_count": total_event_count,
            "is_reliable": is_reliable,
        }
