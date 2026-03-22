"""POS データからの TrustEvent 自動生成（ルールベース）。

設計書 §2.3 に基づく自動生成経路。
返品発生から商品信頼のネガティブ TrustEvent を生成する。

入力: Purchase 辞書リスト
出力: TrustEvent 辞書リスト
制約:
    - generated_by = "rule" を記録する（AI 生成との区別）
    - confidence = 1.0（ルールベースは確信度最大）
    - needs_review = False（ルールベースは人間レビュー不要）
    - スタッフ個人を特定できる集計を含めない（AGENTS.md 禁止事項）
    - AI 解釈を伴う処理は含めない（別バッチの責務）

Note:
    Phase 2 以降で再来店間隔の異常延長検知等を追加予定。
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# 返品理由 → severity マッピング（設計書 §2.4 重みテーブルに準拠）
_RETURN_REASON_SEVERITY: dict[str, int] = {
    "品質問題": 3,
    "説明との相違": 2,
    "サイズ不一致": 2,
    "気が変わった": 1,
    "その他": 1,
}


def detect_return_trust_event(
    purchase: dict[str, Any],
) -> dict[str, Any] | None:
    """返品発生から商品信頼の TrustEvent を生成する。

    Args:
        purchase: Purchase テーブルのレコード辞書

    Returns:
        TrustEvent 辞書。返品でない場合は None。

    Note:
        ルールベース生成のため generated_by = "rule"、
        confidence = 1.0、needs_review = False を設定する。
        AI 解釈結果ではないため confidence チェックは不要だが、
        確定事実として扱わないためのフラグは統一して設定する。
    """
    if not purchase.get("return_flag"):
        return None

    reason = purchase.get("return_reason_category") or "その他"
    severity = _RETURN_REASON_SEVERITY.get(reason, 1)

    return {
        "trust_event_id": str(uuid.uuid4()),
        "store_id": purchase.get("store_id"),
        "source_type": "purchase",
        "source_id": purchase.get("purchase_id"),
        "trust_dimension": "product",
        "sentiment": "negative",
        "severity": severity,
        "theme_tags": [reason],
        "generated_summary": f"商品返品: {purchase.get('product_category') or '不明'} ({reason})",
        "interpretation": None,
        "trait_signal": None,
        "state_signal": None,
        "meta_signal": None,
        "confidence": 1.0,
        "needs_review": False,
        "reviewed_flag": False,
        "generated_by": "rule",
        "detected_at": purchase.get("return_date") or datetime.now(UTC).isoformat(),
    }


def generate_trust_events_from_purchase(
    purchases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Purchase レコード群から TrustEvent リストを生成する。

    Args:
        purchases: Purchase レコードリスト

    Returns:
        生成された TrustEvent 辞書のリスト
    """
    events: list[dict[str, Any]] = []
    for purchase in purchases:
        event = detect_return_trust_event(purchase)
        if event is not None:
            events.append(event)
            logger.info(
                "返品 TrustEvent 生成: store_id=%s, category=%s, severity=%d",
                purchase.get("store_id"),
                purchase.get("product_category"),
                event["severity"],
            )

    logger.info("TrustEvent 生成完了: %d 件", len(events))
    return events
