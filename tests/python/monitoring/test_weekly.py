"""週次チェックのユニットテスト。

対象: src/python/monitoring/checks/weekly.py
テスト観点: スコア異常変動、データ充足度、unreliable 店舗数

Note:
    DB はモックで検証する。
"""

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock

from src.python.monitoring.checks.weekly import (
    check_data_sufficiency,
    check_score_anomaly,
    check_unreliable_stores,
)
from src.python.monitoring.common import CheckStatus


class TestCheckScoreAnomaly:
    """スコア異常変動検知。"""

    def test_変動なしでOK(self) -> None:
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        store_id = uuid.uuid4()
        mock_conn.execute.return_value.fetchall.return_value = [
            (store_id, date.today(), 55.0),
            (store_id, date.today() - timedelta(weeks=1), 54.0),
        ]
        result = check_score_anomaly(mock_engine)
        assert result.status == CheckStatus.OK

    def test_大幅変動でWARN(self) -> None:
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        store_id = uuid.uuid4()
        mock_conn.execute.return_value.fetchall.return_value = [
            (store_id, date.today(), 65.0),
            (store_id, date.today() - timedelta(weeks=1), 50.0),
        ]
        result = check_score_anomaly(mock_engine, anomaly_threshold=10.0)
        assert result.status == CheckStatus.WARN


class TestCheckDataSufficiency:
    """データ充足度確認。"""

    def test_全店舗充足でOK(self) -> None:
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchall.return_value = [
            (uuid.uuid4(), "渋谷店", 15),
            (uuid.uuid4(), "新宿店", 12),
        ]
        result = check_data_sufficiency(mock_engine, min_events_per_store=10)
        assert result.status == CheckStatus.OK

    def test_不足店舗ありでWARN(self) -> None:
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchall.return_value = [
            (uuid.uuid4(), "渋谷店", 15),
            (uuid.uuid4(), "銀座店", 3),
        ]
        result = check_data_sufficiency(mock_engine, min_events_per_store=10)
        assert result.status == CheckStatus.WARN
        assert "銀座店" in result.message


class TestCheckUnreliableStores:
    """unreliable 店舗数確認。"""

    def test_全店舗reliableでOK(self) -> None:
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.scalar.side_effect = [0, 3]
        result = check_unreliable_stores(mock_engine)
        assert result.status == CheckStatus.OK

    def test_unreliableありでWARN(self) -> None:
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.scalar.side_effect = [1, 3]
        result = check_unreliable_stores(mock_engine)
        assert result.status == CheckStatus.WARN
