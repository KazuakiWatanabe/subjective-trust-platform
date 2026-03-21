"""日次チェックのユニットテスト。

対象: src/python/monitoring/checks/daily.py
テスト観点: パイプライン実行確認、needs_review 率、POS 連携確認

Note:
    DB はモックで検証する。
"""

from datetime import date
from unittest.mock import MagicMock

from src.python.monitoring.checks.daily import (
    check_needs_review_rate,
    check_pipeline_execution,
    check_pos_sync,
)
from src.python.monitoring.common import CheckStatus


def _mock_engine_with_results(*query_results: list[tuple[object, ...]]) -> MagicMock:
    """複数クエリの結果を順番に返すモックエンジンを生成する。"""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    results = []
    for qr in query_results:
        mock_result = MagicMock()
        mock_result.scalar.return_value = qr[0] if len(qr) == 1 else None
        mock_result.fetchone.return_value = qr if len(qr) > 1 else None
        results.append(mock_result)

    mock_conn.execute.side_effect = results
    return mock_engine


class TestCheckPipelineExecution:
    """パイプライン実行確認。"""

    def test_全件処理済みでOK(self) -> None:
        engine = _mock_engine_with_results((5,), (0,))
        result = check_pipeline_execution(engine, target_date=date(2026, 3, 20))
        assert result.status == CheckStatus.OK

    def test_未処理ありでWARN(self) -> None:
        engine = _mock_engine_with_results((3,), (2,))
        result = check_pipeline_execution(engine, target_date=date(2026, 3, 20))
        assert result.status == CheckStatus.WARN
        assert "未処理" in result.message


class TestCheckNeedsReviewRate:
    """needs_review 率確認。"""

    def test_正常率でOK(self) -> None:
        engine = _mock_engine_with_results((10, 1))
        result = check_needs_review_rate(engine, target_date=date(2026, 3, 20))
        assert result.status == CheckStatus.OK

    def test_高率でWARN(self) -> None:
        engine = _mock_engine_with_results((10, 5))
        result = check_needs_review_rate(engine, target_date=date(2026, 3, 20))
        assert result.status == CheckStatus.WARN


class TestCheckPosSync:
    """POS 連携確認。"""

    def test_データありでOK(self) -> None:
        engine = _mock_engine_with_results((15,))
        result = check_pos_sync(engine, target_date=date(2026, 3, 20))
        assert result.status == CheckStatus.OK

    def test_データなしでWARN(self) -> None:
        engine = _mock_engine_with_results((0,))
        result = check_pos_sync(engine, target_date=date(2026, 3, 20))
        assert result.status == CheckStatus.WARN
