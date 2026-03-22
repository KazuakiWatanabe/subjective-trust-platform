"""クリティカルチェックのユニットテスト。

対象: src/python/monitoring/checks/critical.py
テスト観点: バッチ処理時間超過、Snapshot更新漏れ、TrustEvent重複

Note:
    DB はモックで検証する。
"""

from unittest.mock import MagicMock, patch

from src.python.monitoring.checks.critical import (
    check_batch_duration,
    check_duplicate_trust_events,
    check_snapshot_completeness,
)
from src.python.monitoring.common import CheckStatus


def _mock_db_context(cursor_results: list[dict[str, object] | None]) -> MagicMock:
    """get_db() のモックを生成する。"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = cursor_results
    mock_cursor.fetchall.side_effect = cursor_results
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return mock_conn


class TestCheckBatchDuration:
    """バッチ処理時間超過。"""

    @patch("src.python.monitoring.checks.critical.slack_alert")
    @patch("src.python.monitoring.checks.critical.get_db")
    def test_正常時間でOK(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([
            {"duration_min": 5.0, "processed_count": 100},  # latest
            {"median_min": 4.0},  # stats
        ])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_batch_duration("test_batch")
        assert result.status == CheckStatus.OK
        mock_slack.assert_not_called()

    @patch("src.python.monitoring.checks.critical.slack_alert")
    @patch("src.python.monitoring.checks.critical.get_db")
    def test_超過でCRITICAL(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([
            {"duration_min": 45.0, "processed_count": 100},  # latest
            {"median_min": 10.0},  # stats → threshold=30
        ])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_batch_duration("test_batch")
        assert result.status == CheckStatus.CRITICAL
        mock_slack.assert_called_once()


class TestCheckSnapshotCompleteness:
    """Snapshot 更新漏れ。"""

    @patch("src.python.monitoring.checks.critical.slack_alert")
    @patch("src.python.monitoring.checks.critical.get_db")
    def test_全店舗更新済みでOK(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([[]])  # missing = empty
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_snapshot_completeness()
        assert result.status == CheckStatus.OK

    @patch("src.python.monitoring.checks.critical.slack_alert")
    @patch("src.python.monitoring.checks.critical.get_db")
    def test_欠損ありでCRITICAL(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([[{"store_id": "xxx", "store_name": "渋谷店"}]])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_snapshot_completeness()
        assert result.status == CheckStatus.CRITICAL
        mock_slack.assert_called_once()


class TestCheckDuplicateTrustEvents:
    """TrustEvent 重複検知。"""

    @patch("src.python.monitoring.checks.critical.slack_alert")
    @patch("src.python.monitoring.checks.critical.get_db")
    def test_重複なしでOK(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([[]])  # duplicates = empty
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_duplicate_trust_events()
        assert result.status == CheckStatus.OK

    @patch("src.python.monitoring.checks.critical.slack_alert")
    @patch("src.python.monitoring.checks.critical.get_db")
    def test_重複ありでCRITICAL(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([[
            {"source_type": "feedback", "source_id": "xxx", "trust_dimension": "service", "cnt": 2}
        ]])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_duplicate_trust_events()
        assert result.status == CheckStatus.CRITICAL
