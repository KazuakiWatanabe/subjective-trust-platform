"""監視共通ユーティリティ。

DB 接続・Slack 通知・バッチジョブ記録の共通関数を提供する。

Note:
    監視スクリプトは同期実行のため psycopg2 を使用する。
    Slack Webhook URL は環境変数 SLACK_WEBHOOK_URL で設定する。
    未設定の場合はログ出力のみ行い、通知はスキップする。
"""

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import psycopg2
import psycopg2.extras
import requests
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# 環境変数
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://trust_user:trust_pass@localhost:5432/trust_platform",
)
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
SLACK_CHANNEL_OPS = os.environ.get("SLACK_CHANNEL_OPS", "#trust-platform-alerts")
SLACK_CHANNEL_PDM = os.environ.get("SLACK_CHANNEL_PDM", "#trust-platform-weekly")


class CheckStatus(Enum):
    """チェック結果のステータス。"""

    OK = "ok"
    WARN = "warn"
    CRITICAL = "critical"
    ERROR = "error"


@dataclass
class CheckResult:
    """監視チェック結果。"""

    name: str
    status: CheckStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def is_ok(self) -> bool:
        """ステータスが OK かどうかを返す。"""
        return self.status == CheckStatus.OK


def _get_psycopg2_url() -> str:
    """psycopg2 用の接続 URL を返す。asyncpg 形式は自動変換する。"""
    url = DATABASE_URL
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgresql+psycopg2://", "postgresql://")
    return url


@contextmanager
def get_db() -> Generator[Any, None, None]:
    """psycopg2 の DB 接続コンテキストマネージャ。

    Yields:
        psycopg2 connection（RealDictCursor）
    """
    conn = psycopg2.connect(_get_psycopg2_url(), cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_sync_engine() -> Engine:
    """SQLAlchemy 同期エンジンを返す（後方互換用）。"""
    url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    return create_engine(url)


def slack_alert(
    message: str,
    level: str = "warning",
    channel: str | None = None,
) -> None:
    """Slack Webhook でアラートを送信する。

    Args:
        message: 通知メッセージ（Markdown 対応）
        level: "critical" | "warning" | "info"
        channel: 送信先チャンネル（None の場合は SLACK_CHANNEL_OPS）

    Note:
        SLACK_WEBHOOK_URL が未設定の場合はログ出力のみ。
    """
    emoji = {
        "critical": ":red_circle:",
        "warning": ":warning:",
        "info": ":large_green_circle:",
    }.get(level, ":white_circle:")
    target = channel or SLACK_CHANNEL_OPS

    if not SLACK_WEBHOOK_URL:
        logger.info("[%s] %s %s", target, emoji, message)
        return

    payload = {
        "channel": target,
        "text": f"{emoji} *[Trust Platform]* {message}",
    }

    try:
        resp = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=5)
        resp.raise_for_status()
        logger.info("Slack 通知送信成功: %s", target)
    except Exception as e:
        logger.error("Slack 通知送信失敗: %s", e)


def record_job_start(conn: Any, job_name: str, store_id: str | None = None) -> str:
    """バッチジョブの開始を記録する。

    Args:
        conn: psycopg2 connection
        job_name: ジョブ名
        store_id: 店舗 ID（全店舗対象の場合は None）

    Returns:
        log_id（UUID 文字列）
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO batch_job_logs (job_name, store_id, started_at, status)
            VALUES (%s, %s, NOW(), 'running')
            RETURNING log_id
            """,
            (job_name, store_id),
        )
        row = cur.fetchone()
        log_id = str(row["log_id"]) if isinstance(row, dict) else str(row[0])
        conn.commit()
        logger.info("ジョブ開始記録: job_name=%s, log_id=%s", job_name, log_id)
        return log_id


def record_job_end(
    conn: Any,
    log_id: str,
    processed_count: int,
    error: str | None = None,
    api_cost_jpy: float | None = None,
) -> None:
    """バッチジョブの終了を記録する。

    Args:
        conn: psycopg2 connection
        log_id: record_job_start で返された log_id
        processed_count: 処理件数
        error: エラーメッセージ（None の場合は completed）
        api_cost_jpy: API コスト（円）
    """
    status = "failed" if error else "completed"
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE batch_job_logs
            SET finished_at = NOW(),
                status = %s,
                processed_count = %s,
                error_message = %s,
                api_cost_jpy = %s
            WHERE log_id = %s::uuid
            """,
            (status, processed_count, error, api_cost_jpy, log_id),
        )
        conn.commit()
        logger.info(
            "ジョブ終了記録: log_id=%s, status=%s, count=%d", log_id, status, processed_count
        )
