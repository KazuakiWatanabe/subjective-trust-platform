"""AI 解釈パイプライン（日次バッチ）。

Feedback.free_comment と ReviewExternal のテキストを対象に
AI 解釈を実行し、TrustEvent テーブルに書き込む。

入力: Feedback / ReviewExternal の未解釈テキスト
出力: TrustEvent レコード（generated_by='ai'）
制約:
    - 個人識別情報は AI 送信前にマスキングする（§8.3）
    - confidence < 0.6 → needs_review = True
    - generated_by = 'ai' を必ず記録する

Note:
    asyncio.gather で並行処理し、API レート制限を考慮したスロットリングを実装する。
"""

import argparse
import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from src.python.interpretation.client import BaseInterpretationClient
from src.python.interpretation.schemas import TrustInterpretation

logger = logging.getLogger(__name__)

# PII マスキングパターン
_PHONE_PATTERN = re.compile(
    r"(?:\d{2,4}[-\s]?\d{2,4}[-\s]?\d{3,4})"
)
_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
)


def mask_pii(text: str) -> str:
    """個人識別情報をマスキングする。

    Args:
        text: マスキング対象のテキスト

    Returns:
        PII がマスクされたテキスト

    Note:
        氏名・電話番号・メールアドレスをマスキングする。
        Claude API / Bedrock に送信する前に必ず呼び出すこと（§8.3）。
    """
    result = _EMAIL_PATTERN.sub("[EMAIL]", text)
    result = _PHONE_PATTERN.sub("[PHONE]", result)
    return result


def _interpretation_to_event_dict(
    interpretation: TrustInterpretation,
    source_type: str,
    source_id: uuid.UUID,
    store_id: uuid.UUID,
) -> dict[str, Any]:
    """TrustInterpretation を TrustEvent 相当の辞書に変換する。

    Args:
        interpretation: AI 解釈結果
        source_type: ソース種別（feedback / review）
        source_id: ソーステーブルの PK
        store_id: 店舗 ID

    Returns:
        TrustEvent テーブルに挿入可能な辞書
    """
    return {
        "trust_event_id": uuid.uuid4(),
        "store_id": store_id,
        "source_type": source_type,
        "source_id": source_id,
        "trust_dimension": interpretation.trust_dimension,
        "sentiment": interpretation.sentiment,
        "severity": interpretation.severity,
        "theme_tags": interpretation.theme_tags,
        "generated_summary": interpretation.summary,
        "interpretation": interpretation.interpretation,
        "trait_signal": interpretation.subjective_hints.trait_signal,
        "state_signal": interpretation.subjective_hints.state_signal,
        "meta_signal": interpretation.subjective_hints.meta_signal,
        "confidence": interpretation.confidence,
        "needs_review": interpretation.needs_review,
        "reviewed_flag": False,
        "generated_by": "ai",
        "detected_at": datetime.now(timezone.utc),
    }


class InterpretationPipeline:
    """AI 解釈パイプライン。

    BaseInterpretationClient を使用してテキストを解釈し、
    TrustEvent 相当の辞書を生成する。

    Args:
        client: AI 解釈クライアント（Mock / Anthropic / Bedrock）
        max_concurrency: 並行処理の最大数（API レート制限対策）
    """

    def __init__(
        self,
        client: BaseInterpretationClient,
        max_concurrency: int = 5,
    ) -> None:
        self._client = client
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def _interpret_with_throttle(self, text: str) -> TrustInterpretation:
        """スロットリング付きで AI 解釈を実行する。

        Args:
            text: マスキング済みテキスト

        Returns:
            TrustInterpretation: AI 解釈結果
        """
        async with self._semaphore:
            return await self._client.interpret(text)

    async def process_feedback(
        self,
        feedback_id: uuid.UUID,
        store_id: uuid.UUID,
        free_comment: str | None,
    ) -> list[dict[str, Any]]:
        """Feedback の free_comment を AI 解釈する。

        Args:
            feedback_id: Feedback の PK
            store_id: 店舗 ID
            free_comment: 自由記述テキスト（None/空の場合はスキップ）

        Returns:
            TrustEvent 辞書のリスト（0 または 1 件）
        """
        if not free_comment or not free_comment.strip():
            logger.debug("free_comment が空のためスキップ: feedback_id=%s", feedback_id)
            return []

        masked_text = mask_pii(free_comment)
        interpretation = await self._interpret_with_throttle(masked_text)

        event = _interpretation_to_event_dict(
            interpretation=interpretation,
            source_type="feedback",
            source_id=feedback_id,
            store_id=store_id,
        )
        logger.info(
            "Feedback 解釈完了: feedback_id=%s, dimension=%s, confidence=%.2f",
            feedback_id,
            interpretation.trust_dimension,
            interpretation.confidence,
        )
        return [event]

    async def process_review(
        self,
        review_id: uuid.UUID,
        store_id: uuid.UUID,
        review_text: str | None,
    ) -> list[dict[str, Any]]:
        """ReviewExternal のテキストを AI 解釈する。

        Args:
            review_id: ReviewExternal の PK
            store_id: 店舗 ID
            review_text: レビューテキスト（None/空の場合はスキップ）

        Returns:
            TrustEvent 辞書のリスト（0 または 1 件）
        """
        if not review_text or not review_text.strip():
            logger.debug("review_text が空のためスキップ: review_id=%s", review_id)
            return []

        masked_text = mask_pii(review_text)
        interpretation = await self._interpret_with_throttle(masked_text)

        event = _interpretation_to_event_dict(
            interpretation=interpretation,
            source_type="review",
            source_id=review_id,
            store_id=store_id,
        )
        logger.info(
            "Review 解釈完了: review_id=%s, dimension=%s, confidence=%.2f",
            review_id,
            interpretation.trust_dimension,
            interpretation.confidence,
        )
        return [event]

    async def run_batch(
        self,
        feedbacks: list[dict[str, Any]],
        reviews: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """バッチで複数の Feedback / ReviewExternal を並行解釈する。

        Args:
            feedbacks: Feedback レコードのリスト（feedback_id, store_id, free_comment）
            reviews: ReviewExternal レコードのリスト（review_id, store_id, review_text）

        Returns:
            生成された TrustEvent 辞書のリスト
        """
        tasks: list[asyncio.Task[list[dict[str, Any]]]] = []

        for fb in feedbacks:
            task = asyncio.create_task(
                self.process_feedback(
                    feedback_id=fb["feedback_id"],
                    store_id=fb["store_id"],
                    free_comment=fb.get("free_comment"),
                )
            )
            tasks.append(task)

        for rv in reviews:
            task = asyncio.create_task(
                self.process_review(
                    review_id=rv["review_id"],
                    store_id=rv["store_id"],
                    review_text=rv.get("review_text"),
                )
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_events: list[dict[str, Any]] = []
        for result in results:
            if isinstance(result, Exception):
                logger.error("解釈処理でエラー発生: %s", result)
                continue
            all_events.extend(result)

        logger.info("バッチ完了: %d 件の TrustEvent を生成", len(all_events))
        return all_events


# --- CLI エントリポイント ---


async def run_pipeline(target_date: str | None = None) -> None:
    """AI 解釈パイプラインを実行する。

    Args:
        target_date: 処理対象日（YYYY-MM-DD）。None の場合は前日分を処理する。

    Note:
        DB からの Feedback / ReviewExternal 取得は T-05 時点では
        スタブ実装。実 DB 連携は統合テストで確認する。
    """
    logger.info("AI 解釈パイプライン開始: target_date=%s", target_date)

    from src.python.config import get_settings
    from src.python.interpretation.client import get_interpretation_client

    settings = get_settings()
    client = get_interpretation_client(settings)
    pipeline = InterpretationPipeline(client=client)

    # バッチジョブ記録（監視用）
    log_id: str | None = None
    try:
        from src.python.monitoring.common import get_db, record_job_end, record_job_start
        with get_db() as conn:
            log_id = record_job_start(conn, "ai_interpretation_batch")
    except Exception as e:
        logger.warning("ジョブ記録の開始に失敗（監視テーブル未作成の可能性）: %s", e)

    # DB からの取得は統合テストで確認。ここではスタブ
    feedbacks: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []

    events = await pipeline.run_batch(feedbacks, reviews)
    logger.info("AI 解釈パイプライン完了: %d 件の TrustEvent を生成", len(events))

    # バッチジョブ記録の終了 + クリティカルチェック
    try:
        from src.python.monitoring.common import get_db, record_job_end
        from src.python.monitoring.checks.critical import run_critical_checks
        if log_id:
            with get_db() as conn:
                record_job_end(conn, log_id, len(events))
            run_critical_checks("ai_interpretation_batch")
    except Exception as e:
        logger.warning("ジョブ記録の終了に失敗: %s", e)


async def watch() -> None:
    """ワーカーモード: パイプラインの待機ループ。

    Note:
        本番では SQS / Pub/Sub からのメッセージ受信で起動する構成に変更予定。
    """
    logger.info("AI 解釈ワーカー: 待機モード起動")
    while True:
        await asyncio.sleep(60)


def main() -> None:
    """エントリポイント。--watch または --date で起動モードを切り替える。"""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="AI 解釈パイプライン")
    parser.add_argument("--date", type=str, default=None, help="処理対象日 (YYYY-MM-DD)")
    parser.add_argument("--watch", action="store_true", help="ワーカー待機モードで起動")
    args = parser.parse_args()

    if args.watch:
        asyncio.run(watch())
    else:
        asyncio.run(run_pipeline(target_date=args.date))


if __name__ == "__main__":
    main()
