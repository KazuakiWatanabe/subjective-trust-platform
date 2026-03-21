"""監視共通ユーティリティ。

監視チェック結果の構造体、DB 接続ヘルパー、Slack 通知関数を提供する。

Note:
    Slack Webhook URL は環境変数 SLACK_WEBHOOK_URL で設定する。
    未設定の場合はログ出力のみ行い、通知はスキップする。
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import requests
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class CheckStatus(Enum):
    """チェック結果のステータス。"""

    OK = "ok"
    WARN = "warn"
    CRITICAL = "critical"
    ERROR = "error"


@dataclass
class CheckResult:
    """監視チェック結果。

    Args:
        name: チェック名
        status: 結果ステータス
        message: 人間向けの結果メッセージ
        details: 追加の詳細情報（任意）
        checked_at: チェック実行日時
    """

    name: str
    status: CheckStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_ok(self) -> bool:
        """ステータスが OK かどうかを返す。"""
        return self.status == CheckStatus.OK


def get_sync_engine() -> Engine:
    """同期接続用の SQLAlchemy エンジンを返す。

    Returns:
        Engine: psycopg2 ベースの同期エンジン

    Note:
        監視スクリプトは同期実行のため、asyncpg ではなく psycopg2 を使用する。
        DATABASE_URL が asyncpg 形式の場合は自動で psycopg2 形式に変換する。
    """
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg2://trust_user:trust_pass@localhost:5432/trust_platform",
    )
    # asyncpg → psycopg2 に変換
    url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    return create_engine(url)


def check_db_connection(engine: Engine) -> CheckResult:
    """DB 接続チェック。

    Args:
        engine: SQLAlchemy エンジン

    Returns:
        CheckResult
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return CheckResult(
            name="db_connection",
            status=CheckStatus.OK,
            message="DB 接続正常",
        )
    except Exception as e:
        return CheckResult(
            name="db_connection",
            status=CheckStatus.CRITICAL,
            message=f"DB 接続失敗: {e}",
        )


def send_slack_notification(
    results: list[CheckResult],
    channel_label: str = "monitoring",
) -> None:
    """Slack Webhook でチェック結果を通知する。

    Args:
        results: チェック結果リスト
        channel_label: 通知元のラベル

    Note:
        SLACK_WEBHOOK_URL が未設定の場合はログ出力のみ。
        通信先: Slack Webhook URL（allowlist 追加が必要な場合は AGENTS.md を更新すること）
    """
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.info("SLACK_WEBHOOK_URL 未設定: Slack 通知スキップ")
        for r in results:
            logger.info("[%s] %s: %s — %s", channel_label, r.status.value, r.name, r.message)
        return

    # 異常のある結果のみ通知
    alerts = [r for r in results if not r.is_ok()]
    if not alerts:
        logger.info("[%s] 全チェック正常、Slack 通知なし", channel_label)
        return

    blocks = []
    for r in alerts:
        emoji = ":red_circle:" if r.status == CheckStatus.CRITICAL else ":warning:"
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji} *{r.name}* [{r.status.value}]\n{r.message}",
            },
        })

    payload = {
        "text": f"[{channel_label}] {len(alerts)} 件のアラート",
        "blocks": blocks,
    }

    try:
        resp = requests.post(
            webhook_url,
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("[%s] Slack 通知送信成功: %d 件", channel_label, len(alerts))
    except Exception as e:
        logger.error("[%s] Slack 通知送信失敗: %s", channel_label, e)
