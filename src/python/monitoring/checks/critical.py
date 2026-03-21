"""クリティカルチェック（5分間隔）。

API ヘルスチェック・DB 接続・テーブル存在確認を行う。
異常時は即座に Slack 通知する。

Note:
    これらのチェックはシステムの基本的な稼働を確認するもので、
    失敗した場合は即座に対応が必要。
"""

import logging

import requests
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.python.monitoring.common import CheckResult, CheckStatus

logger = logging.getLogger(__name__)

# 期待されるテーブル一覧（設計書 §4.2）
EXPECTED_TABLES = [
    "store",
    "staff",
    "customer",
    "visit",
    "feedback",
    "trust_event",
    "trust_score_snapshot",
    "purchase",
    "complaint_inquiry",
    "review_external",
]


def check_api_health(base_url: str = "http://localhost:8080") -> CheckResult:
    """API ヘルスチェック。

    Args:
        base_url: API のベース URL

    Returns:
        CheckResult
    """
    try:
        resp = requests.get(f"{base_url}/health", timeout=5)
        if resp.status_code == 200:
            body = resp.json()
            return CheckResult(
                name="api_health",
                status=CheckStatus.OK,
                message=f"API 正常: environment={body.get('environment')}, ai_backend={body.get('ai_backend')}",
            )
        return CheckResult(
            name="api_health",
            status=CheckStatus.CRITICAL,
            message=f"API 異常: HTTP {resp.status_code}",
        )
    except requests.ConnectionError:
        return CheckResult(
            name="api_health",
            status=CheckStatus.CRITICAL,
            message="API 接続不可: サーバーが起動していない可能性",
        )
    except Exception as e:
        return CheckResult(
            name="api_health",
            status=CheckStatus.ERROR,
            message=f"API チェックエラー: {e}",
        )


def check_tables_exist(engine: Engine) -> CheckResult:
    """全テーブル存在確認。

    Args:
        engine: SQLAlchemy エンジン

    Returns:
        CheckResult
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
            existing = {row[0] for row in result}

        missing = [t for t in EXPECTED_TABLES if t not in existing]
        if missing:
            return CheckResult(
                name="tables_exist",
                status=CheckStatus.CRITICAL,
                message=f"テーブル欠損: {', '.join(missing)}",
                details={"missing": missing, "existing": list(existing)},
            )
        return CheckResult(
            name="tables_exist",
            status=CheckStatus.OK,
            message=f"全 {len(EXPECTED_TABLES)} テーブル存在確認",
        )
    except Exception as e:
        return CheckResult(
            name="tables_exist",
            status=CheckStatus.ERROR,
            message=f"テーブルチェックエラー: {e}",
        )


def run_critical_checks(
    engine: Engine,
    api_base_url: str = "http://localhost:8080",
) -> list[CheckResult]:
    """全クリティカルチェックを実行する。

    Args:
        engine: SQLAlchemy エンジン
        api_base_url: API のベース URL

    Returns:
        CheckResult のリスト
    """
    from src.python.monitoring.common import check_db_connection

    results = [
        check_api_health(api_base_url),
        check_db_connection(engine),
        check_tables_exist(engine),
    ]

    for r in results:
        level = logging.ERROR if not r.is_ok() else logging.INFO
        logger.log(level, "[critical] %s: %s — %s", r.status.value, r.name, r.message)

    return results
