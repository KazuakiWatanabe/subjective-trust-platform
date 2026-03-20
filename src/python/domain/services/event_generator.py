"""TrustEvent 自動生成（ルールベース）。

設計書 §2.3 に基づく手動生成ルール。
接客結果・アンケートスコアから TrustEvent を自動生成する。

入力: Visit 辞書 / Feedback 辞書
出力: TrustEvent 辞書リスト
制約:
    - 同一 source_id から重複イベントを生成しない（冪等性）
    - generated_by = 'rule' を記録する

Note:
    AI 解釈による生成は pipeline.py が担当する。ここではルールベースのみ。
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class RuleBasedEventGenerator:
    """ルールベースの TrustEvent 生成器。

    冪等性を processed_source_ids セットで管理する。

    Note:
        Phase 1 ではインメモリで管理。本番では DB の処理済みテーブルで管理する。
    """

    def __init__(self) -> None:
        self._processed_source_ids: set[uuid.UUID] = set()

    def _make_event(
        self,
        store_id: uuid.UUID,
        source_type: str,
        source_id: uuid.UUID,
        trust_dimension: str,
        sentiment: str,
        severity: int,
        summary: str,
    ) -> dict[str, Any]:
        """TrustEvent 辞書を生成する共通ヘルパー。"""
        return {
            "trust_event_id": uuid.uuid4(),
            "store_id": store_id,
            "source_type": source_type,
            "source_id": source_id,
            "trust_dimension": trust_dimension,
            "sentiment": sentiment,
            "severity": severity,
            "theme_tags": [],
            "generated_summary": summary,
            "interpretation": None,
            "trait_signal": None,
            "state_signal": None,
            "meta_signal": None,
            "confidence": None,
            "needs_review": False,
            "reviewed_flag": False,
            "generated_by": "rule",
            "detected_at": datetime.now(timezone.utc),
        }

    def generate_from_visit(self, visit: dict[str, Any]) -> list[dict[str, Any]]:
        """Visit データからルールベースで TrustEvent を生成する。

        Args:
            visit: Visit 辞書（visit_id, store_id, contact_result, alternative_proposed）

        Returns:
            TrustEvent 辞書のリスト

        Note:
            ルール: contact_result=欠品離脱 かつ alternative_proposed=False
            → 提案信頼のネガティブイベント
        """
        visit_id: uuid.UUID = visit["visit_id"]

        # 冪等性チェック
        if visit_id in self._processed_source_ids:
            logger.debug("スキップ（処理済み）: visit_id=%s", visit_id)
            return []

        events: list[dict[str, Any]] = []
        contact_result = visit.get("contact_result")
        alternative_proposed = visit.get("alternative_proposed")

        # 欠品離脱 + 代替提案なし → 提案信頼ネガティブ
        if contact_result == "out_of_stock_exit" and alternative_proposed is False:
            events.append(
                self._make_event(
                    store_id=visit["store_id"],
                    source_type="visit",
                    source_id=visit_id,
                    trust_dimension="proposal",
                    sentiment="negative",
                    severity=2,
                    summary="欠品離脱: 代替提案なし",
                )
            )

        if events:
            self._processed_source_ids.add(visit_id)
            logger.info(
                "Visit ルールイベント生成: visit_id=%s, %d 件",
                visit_id,
                len(events),
            )

        return events

    def generate_from_feedback(self, feedback: dict[str, Any]) -> list[dict[str, Any]]:
        """Feedback データからルールベースで TrustEvent を生成する。

        Args:
            feedback: Feedback 辞書（feedback_id, store_id, score_revisit）

        Returns:
            TrustEvent 辞書のリスト

        Note:
            ルール:
            - score_revisit 1〜2 → 接客信頼ネガティブ
            - score_revisit 4〜5 → 接客信頼ポジティブ
            - score_revisit 3 → イベント生成なし
        """
        feedback_id: uuid.UUID = feedback["feedback_id"]

        # 冪等性チェック
        if feedback_id in self._processed_source_ids:
            logger.debug("スキップ（処理済み）: feedback_id=%s", feedback_id)
            return []

        events: list[dict[str, Any]] = []
        score_revisit = feedback.get("score_revisit", 3)
        store_id = feedback["store_id"]

        if score_revisit <= 2:
            # 低評価 → 接客信頼ネガティブ
            events.append(
                self._make_event(
                    store_id=store_id,
                    source_type="feedback",
                    source_id=feedback_id,
                    trust_dimension="service",
                    sentiment="negative",
                    severity=2 if score_revisit == 2 else 3,
                    summary=f"再来店意向低評価: score_revisit={score_revisit}",
                )
            )
        elif score_revisit >= 4:
            # 高評価 → 接客信頼ポジティブ
            events.append(
                self._make_event(
                    store_id=store_id,
                    source_type="feedback",
                    source_id=feedback_id,
                    trust_dimension="service",
                    sentiment="positive",
                    severity=1,
                    summary=f"再来店意向高評価: score_revisit={score_revisit}",
                )
            )

        if events:
            self._processed_source_ids.add(feedback_id)
            logger.info(
                "Feedback ルールイベント生成: feedback_id=%s, %d 件",
                feedback_id,
                len(events),
            )

        return events
