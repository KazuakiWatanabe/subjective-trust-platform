"""日次チェックのユニットテスト。

対象: src/python/monitoring/checks/daily.py
テスト観点: 処理件数減少、APIコスト急増、source別ゼロ検知

Note:
    DB はモックで検証する。
"""

from unittest.mock import MagicMock, patch

from src.python.monitoring.checks.daily import (
    check_batch_processed_count,
    check_claude_api_cost,
    check_trust_event_by_source,
)
from src.python.monitoring.common import CheckStatus


def _mock_db_context(cursor_results: list[object]) -> MagicMock:
    """get_db() のモックを生成する。"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = cursor_results
    mock_cursor.fetchall.side_effect = cursor_results
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return mock_conn


class TestCheckBatchProcessedCount:
    """処理件数減少。"""

    @patch("src.python.monitoring.checks.daily.slack_alert")
    @patch("src.python.monitoring.checks.daily.get_db")
    def test_正常件数でOK(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([
            {"processed_count": 80},  # latest
            {"avg_count": 100.0},  # stats
        ])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_batch_processed_count("test_batch")
        assert result.status == CheckStatus.OK

    @patch("src.python.monitoring.checks.daily.slack_alert")
    @patch("src.python.monitoring.checks.daily.get_db")
    def test_件数減少でWARN(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([
            {"processed_count": 30},  # latest: 30 < 100*0.5
            {"avg_count": 100.0},  # stats
        ])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_batch_processed_count("test_batch")
        assert result.status == CheckStatus.WARN

    @patch("src.python.monitoring.checks.daily.slack_alert")
    @patch("src.python.monitoring.checks.daily.get_db")
    def test_件数ゼロでWARN(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([
            {"processed_count": 0},  # latest = 0
        ])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_batch_processed_count("test_batch")
        assert result.status == CheckStatus.WARN


class TestCheckClaudeApiCost:
    """APIコスト急増。"""

    @patch("src.python.monitoring.checks.daily.slack_alert")
    @patch("src.python.monitoring.checks.daily.get_db")
    def test_正常コストでOK(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([
            {"today_cost": 500, "avg_cost": 400},
        ])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_claude_api_cost()
        assert result.status == CheckStatus.OK

    @patch("src.python.monitoring.checks.daily.slack_alert")
    @patch("src.python.monitoring.checks.daily.get_db")
    def test_コスト急増でWARN(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([
            {"today_cost": 700, "avg_cost": 400},  # 700 > 400*1.5
        ])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_claude_api_cost()
        assert result.status == CheckStatus.WARN


class TestCheckTrustEventBySource:
    """source別ゼロ検知。"""

    @patch("src.python.monitoring.checks.daily.slack_alert")
    @patch("src.python.monitoring.checks.daily.get_db")
    def test_全ソースありでOK(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([[
            {"source_type": "visit", "d0": 3, "d1": 2, "d2": 4},
            {"source_type": "feedback", "d0": 1, "d1": 2, "d2": 1},
            {"source_type": "complaint", "d0": 0, "d1": 1, "d2": 0},
            {"source_type": "review", "d0": 2, "d1": 0, "d2": 1},
        ]])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_trust_event_by_source()
        assert result.status == CheckStatus.OK

    @patch("src.python.monitoring.checks.daily.slack_alert")
    @patch("src.python.monitoring.checks.daily.get_db")
    def test_3日連続ゼロでWARN(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([[
            {"source_type": "visit", "d0": 3, "d1": 2, "d2": 4},
            {"source_type": "feedback", "d0": 0, "d1": 0, "d2": 0},
        ]])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_trust_event_by_source()
        assert result.status == CheckStatus.WARN
