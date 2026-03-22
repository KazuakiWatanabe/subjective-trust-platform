"""Google 口コミ解釈バッチ。

未処理の review_external レコードを AI 解釈し、TrustEvent を生成する。

Note:
    AWS Bedrock 経由で Claude API を呼び出す。
    tenacity でリトライ（最大3回・指数バックオフ）。
"""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.python.ai.prompts.review_interpretation import build_review_prompt
from src.python.interpretation.client import BaseInterpretationClient

logger = logging.getLogger(__name__)


def mentions_to_trust_events(
    review_id: uuid.UUID,
    store_id: uuid.UUID,
    review_date: datetime,
    interpretation_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """mentions 配列から TrustEvent 辞書リストを生成する。

    Args:
        review_id: レビュー ID
        store_id: 店舗 ID
        review_date: レビュー投稿日
        interpretation_result: AI 解釈結果

    Returns:
        TrustEvent 辞書のリスト
    """
    events: list[dict[str, Any]] = []
    hints = interpretation_result.get("subjective_hints", {})

    for mention in interpretation_result.get("mentions", []):
        confidence = float(mention.get("confidence", 0.0))
        events.append({
            "trust_event_id": uuid.uuid4(),
            "store_id": store_id,
            "source_type": "review",
            "source_id": review_id,
            "trust_dimension": mention["trust_dimension"],
            "sentiment": mention["sentiment"],
            "severity": mention.get("severity", 1),
            "theme_tags": mention.get("theme_tags", []),
            "generated_summary": mention.get("summary"),
            "interpretation": mention.get("interpretation"),
            "trait_signal": hints.get("trait_signal"),
            "state_signal": hints.get("state_signal"),
            "meta_signal": hints.get("meta_signal"),
            "confidence": confidence,
            "needs_review": confidence < 0.6,
            "reviewed_flag": False,
            "generated_by": "ai",
            "detected_at": review_date,
        })

    return events


async def interpret_review(
    client: BaseInterpretationClient,
    rating: int,
    review_date: str,
    review_text: str,
) -> dict[str, Any]:
    """レビューを AI 解釈する。

    Args:
        client: AI 解釈クライアント
        rating: 評価点
        review_date: 投稿日
        review_text: レビュー本文（PII マスキング済み）

    Returns:
        AI 解釈結果の辞書

    Raises:
        json.JSONDecodeError: AI 出力が JSON でない場合
    """
    prompt = build_review_prompt(rating, review_date, review_text)
    result = await client.interpret(prompt)
    # TrustInterpretation を mentions 形式に変換
    return {
        "mentions": [{
            "trust_dimension": result.trust_dimension,
            "sentiment": result.sentiment,
            "severity": result.severity,
            "theme_tags": result.theme_tags,
            "summary": result.summary,
            "interpretation": result.interpretation,
            "confidence": result.confidence,
        }],
        "subjective_hints": {
            "trait_signal": result.subjective_hints.trait_signal,
            "state_signal": result.subjective_hints.state_signal,
            "meta_signal": result.subjective_hints.meta_signal,
        },
        "overall_sentiment": result.sentiment,
        "review_type": "unknown",
        "contains_competitor_mention": False,
    }


async def run_review_interpret_batch(
    reviews: list[dict[str, Any]],
    client: BaseInterpretationClient,
) -> tuple[list[dict[str, Any]], list[uuid.UUID]]:
    """未処理レビューを解釈しTrustEvent を生成する。

    Args:
        reviews: 未処理レビュー辞書リスト（review_id, store_id, rating, review_text, posted_at）
        client: AI 解釈クライアント

    Returns:
        (TrustEvent 辞書リスト, 処理済み review_id リスト)
    """
    all_events: list[dict[str, Any]] = []
    processed_ids: list[uuid.UUID] = []

    for review in reviews:
        review_id = review["review_id"]
        review_text = review.get("review_text", "")
        if not review_text or not review_text.strip():
            processed_ids.append(review_id)
            continue

        try:
            result = await interpret_review(
                client=client,
                rating=review.get("rating", 0),
                review_date=str(review.get("posted_at", "")),
                review_text=review_text,
            )
            events = mentions_to_trust_events(
                review_id=review_id,
                store_id=review["store_id"],
                review_date=review.get("posted_at", datetime.now(UTC)),
                interpretation_result=result,
            )
            all_events.extend(events)
            processed_ids.append(review_id)

            # スロットリング
            await asyncio.sleep(0.5)

        except json.JSONDecodeError:
            logger.error("JSON 解析エラー: review_id=%s", review_id)
            # needs_review=true で空イベントを生成
            all_events.append({
                "trust_event_id": uuid.uuid4(),
                "store_id": review["store_id"],
                "source_type": "review",
                "source_id": review_id,
                "trust_dimension": "service",
                "sentiment": "neutral",
                "severity": 1,
                "theme_tags": [],
                "generated_summary": "JSON 解析エラーにより手動レビューが必要",
                "interpretation": None,
                "trait_signal": None,
                "state_signal": None,
                "meta_signal": None,
                "confidence": 0.0,
                "needs_review": True,
                "reviewed_flag": False,
                "generated_by": "ai",
                "detected_at": review.get("posted_at", datetime.now(UTC)),
            })
            processed_ids.append(review_id)

        except Exception as e:
            logger.error("解釈エラー: review_id=%s, error=%s", review_id, e)
            all_events.append({
                "trust_event_id": uuid.uuid4(),
                "store_id": review["store_id"],
                "source_type": "review",
                "source_id": review_id,
                "trust_dimension": "service",
                "sentiment": "neutral",
                "severity": 1,
                "theme_tags": [],
                "generated_summary": f"解釈エラー: {e}",
                "interpretation": None,
                "trait_signal": None,
                "state_signal": None,
                "meta_signal": None,
                "confidence": 0.0,
                "needs_review": True,
                "reviewed_flag": False,
                "generated_by": "ai",
                "detected_at": review.get("posted_at", datetime.now(UTC)),
            })
            processed_ids.append(review_id)

    logger.info(
        "解釈バッチ完了: %d 件処理, %d 件 TrustEvent 生成",
        len(processed_ids),
        len(all_events),
    )
    return all_events, processed_ids
