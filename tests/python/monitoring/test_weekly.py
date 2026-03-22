"""週次チェックのユニットテスト。

対象: src/python/monitoring/checks/weekly.py
テスト観点: confidence分布、is_reliable進捗、タグ入力率、レビューキュー

Note:
    DB はモックで検証する。
"""

from unittest.mock import MagicMock, patch

from src.python.monitoring.checks.weekly import (
    check_confidence_distribution,
    check_is_reliable_progress,
    check_review_queue_backlog,
    check_tag_input_rate,
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


class TestCheckConfidenceDistribution:
    """confidence 分布チェック。"""

    @patch("src.python.monitoring.checks.weekly.slack_alert")
    @patch("src.python.monitoring.checks.weekly.get_db")
    def test_正常率でOK(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([
            {"review_ratio": 0.15},  # this_week
            {"avg_ratio": 0.12},  # avg (0.15 < 0.12*1.5=0.18)
        ])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_confidence_distribution()
        assert result.status == CheckStatus.OK

    @patch("src.python.monitoring.checks.weekly.slack_alert")
    @patch("src.python.monitoring.checks.weekly.get_db")
    def test_急増でWARN(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([
            {"review_ratio": 0.35},  # this_week
            {"avg_ratio": 0.12},  # avg (0.35 > 0.12*1.5=0.18)
        ])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_confidence_distribution()
        assert result.status == CheckStatus.WARN


class TestCheckIsReliableProgress:
    """is_reliable 進捗。"""

    @patch("src.python.monitoring.checks.weekly.slack_alert")
    @patch("src.python.monitoring.checks.weekly.get_db")
    def test_全店舗reliableでOK(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([[
            {"store_name": "渋谷店", "reliable_now": True, "reliable_prev": True},
        ]])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_is_reliable_progress()
        assert result.status == CheckStatus.OK

    @patch("src.python.monitoring.checks.weekly.slack_alert")
    @patch("src.python.monitoring.checks.weekly.get_db")
    def test_逆転でWARN(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([[
            {"store_name": "銀座店", "reliable_now": False, "reliable_prev": True},
        ]])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_is_reliable_progress()
        assert result.status == CheckStatus.WARN


class TestCheckTagInputRate:
    """タグ入力率。"""

    @patch("src.python.monitoring.checks.weekly.slack_alert")
    @patch("src.python.monitoring.checks.weekly.get_db")
    def test_全店舗十分でOK(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([[
            {"store_name": "渋谷店", "visit_count": 15},
            {"store_name": "新宿店", "visit_count": 12},
        ]])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_tag_input_rate()
        assert result.status == CheckStatus.OK

    @patch("src.python.monitoring.checks.weekly.slack_alert")
    @patch("src.python.monitoring.checks.weekly.get_db")
    def test_入力不足でWARN(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([[
            {"store_name": "渋谷店", "visit_count": 15},
            {"store_name": "銀座店", "visit_count": 3},
        ]])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_tag_input_rate()
        assert result.status == CheckStatus.WARN


class TestCheckReviewQueueBacklog:
    """レビューキュー滞留。"""

    @patch("src.python.monitoring.checks.weekly.slack_alert")
    @patch("src.python.monitoring.checks.weekly.get_db")
    def test_滞留なしでOK(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([{"total_pending": 10, "overdue_7d": 0}])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_review_queue_backlog()
        assert result.status == CheckStatus.OK

    @patch("src.python.monitoring.checks.weekly.slack_alert")
    @patch("src.python.monitoring.checks.weekly.get_db")
    def test_滞留ありでWARN(self, mock_get_db: MagicMock, mock_slack: MagicMock) -> None:
        conn = _mock_db_context([{"total_pending": 60, "overdue_7d": 5}])
        mock_get_db.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        result = check_review_queue_backlog()
        assert result.status == CheckStatus.WARN
