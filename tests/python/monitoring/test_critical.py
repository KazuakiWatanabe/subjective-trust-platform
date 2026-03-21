"""クリティカルチェックのユニットテスト。

対象: src/python/monitoring/checks/critical.py
テスト観点: API ヘルスチェック、テーブル存在確認

Note:
    実際の DB / API 接続は行わない。モックで検証する。
"""

from unittest.mock import MagicMock, patch

from src.python.monitoring.checks.critical import (
    EXPECTED_TABLES,
    check_api_health,
    check_tables_exist,
)
from src.python.monitoring.common import CheckStatus


class TestCheckApiHealth:
    """API ヘルスチェック。"""

    @patch("src.python.monitoring.checks.critical.requests.get")
    def test_正常応答でOK(self, mock_get: MagicMock) -> None:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "status": "ok", "environment": "local", "ai_backend": "mock"
        }
        result = check_api_health("http://test:8080")
        assert result.status == CheckStatus.OK

    @patch("src.python.monitoring.checks.critical.requests.get")
    def test_500でCRITICAL(self, mock_get: MagicMock) -> None:
        mock_get.return_value.status_code = 500
        result = check_api_health("http://test:8080")
        assert result.status == CheckStatus.CRITICAL

    @patch("src.python.monitoring.checks.critical.requests.get")
    def test_接続不可でCRITICAL(self, mock_get: MagicMock) -> None:
        import requests
        mock_get.side_effect = requests.ConnectionError()
        result = check_api_health("http://test:8080")
        assert result.status == CheckStatus.CRITICAL


class TestCheckTablesExist:
    """テーブル存在確認。"""

    def test_全テーブル存在でOK(self) -> None:
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        # 全テーブル + alembic_version を返す
        mock_conn.execute.return_value = [
            (t,) for t in EXPECTED_TABLES + ["alembic_version", "batch_job_logs"]
        ]
        result = check_tables_exist(mock_engine)
        assert result.status == CheckStatus.OK

    def test_テーブル欠損でCRITICAL(self) -> None:
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        # store テーブルだけ返す
        mock_conn.execute.return_value = [("store",), ("alembic_version",)]
        result = check_tables_exist(mock_engine)
        assert result.status == CheckStatus.CRITICAL
        assert "テーブル欠損" in result.message
