"""POS 日次バッチ（バッチ実行層）。

設計書 §5.3 に基づく POS データの日次取り込みバッチ。
POS 生データを正規化し、Purchase テーブル形式に変換する。

入力: POS 生データ辞書リスト
出力: (正規化済み Purchase 辞書リスト, スキップ件数)
制約:
    - pos_transaction_id で重複チェックを行い冪等性を保証する
    - 不正データはスキップし、バッチ全体は継続する
    - スタッフ個人を特定できる集計は行わない（設計書 §8.2）

Note:
    Phase 1 ではモックデータで動作確認する。
    batch_job_logs への記録は DB 接続時のみ行う。
"""

# TODO(phase2): C# 移管予定 — POS 連携バッチ（業務ロジック部分）

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def normalize_pos_record(
    raw: dict[str, Any],
    store_id: uuid.UUID,
) -> dict[str, Any] | None:
    """POS 生データを Purchase テーブル形式に正規化する。

    Args:
        raw: POS システムから取得した生データ
        store_id: 店舗 ID

    Returns:
        正規化済み辞書。不正データの場合は None を返しスキップする。

    Note:
        customer_id が NULL の場合（匿名来店）はそのまま NULL で保存する。
        スタッフ個人を特定できる集計は行わない（設計書 §8.2）。
    """
    # 必須フィールドの検証
    pos_transaction_id = raw.get("pos_transaction_id")
    if not pos_transaction_id:
        logger.warning("スキップ: pos_transaction_id が欠落: %s", raw)
        return None

    visit_id = raw.get("visit_id")
    if not visit_id:
        logger.warning("スキップ: visit_id が欠落: pos_transaction_id=%s", pos_transaction_id)
        return None

    # TODO(phase2): C# 移管予定 — Purchase リポジトリ
    return {
        "purchase_id": str(uuid.uuid4()),
        "pos_transaction_id": pos_transaction_id,
        "store_id": str(store_id),
        "visit_id": visit_id,
        "product_category": raw.get("product_category"),
        "amount": raw.get("amount"),
        "discount_amount": raw.get("discount_amount"),
        "purchased_at": raw.get("purchased_at"),
        "return_flag": raw.get("return_flag", False),
        "return_reason_category": raw.get("return_reason_category"),
        "return_date": raw.get("return_date"),
        "customer_id": raw.get("customer_id"),
    }


async def run_pos_sync_batch(
    raw_records: list[dict[str, Any]],
    store_id: uuid.UUID,
    existing_pos_ids: set[str],
) -> tuple[list[dict[str, Any]], int]:
    """POS 日次バッチ。正規化・重複チェック・保存を行う。

    Args:
        raw_records: POS から取得した生レコードリスト
        store_id: 店舗 ID
        existing_pos_ids: DB 保存済みの pos_transaction_id セット（冪等性保証）

    Returns:
        (保存済みレコードリスト, スキップ件数)

    Note:
        batch_job_logs に record_job_start / record_job_end を記録する。
        バッチ末尾で run_critical_checks("pos_sync_batch") を呼び出す。
    """
    saved: list[dict[str, Any]] = []
    skipped = 0

    for raw in raw_records:
        # 正規化（不正データは None）
        normalized = normalize_pos_record(raw, store_id)
        if normalized is None:
            skipped += 1
            continue

        # 冪等性チェック: 既存の pos_transaction_id はスキップ
        pos_txn_id = normalized["pos_transaction_id"]
        if pos_txn_id in existing_pos_ids:
            logger.debug("スキップ（処理済み）: pos_transaction_id=%s", pos_txn_id)
            skipped += 1
            continue

        saved.append(normalized)
        # バッチ内での重複も防止
        existing_pos_ids.add(pos_txn_id)

    logger.info(
        "POS 同期完了: store_id=%s, 保存=%d件, スキップ=%d件",
        store_id,
        len(saved),
        skipped,
    )

    return saved, skipped
