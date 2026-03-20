"""アラート生成バッチのユニットテスト。

対象: src/python/domain/services/alert_generator.py
テスト観点: 4種のアラート閾値判定、アラート内容の構成

Note:
    設計書 §7.1 のアラート閾値を検証する。
"""

import pytest

from src.python.domain.services.alert_generator import (
    Alert,
    AlertGenerator,
)


class TestExitRateAlert:
    """AC-01: 接客後離脱率が前4週平均×1.5超でアラートが生成される。"""

    # AC-01: 閾値超過でアラート生成
    def test_離脱率が閾値超過でアラート生成(self) -> None:
        """今週の離脱率が前4週平均×1.5 を超えるとアラートが生成される。"""
        gen = AlertGenerator()
        # 前4週: [0.10, 0.12, 0.08, 0.10] → 平均 0.10 → 閾値 0.15
        weekly_exit_rates = [0.10, 0.12, 0.08, 0.10, 0.20]  # 今週 0.20 > 0.15
        alerts = gen.check_exit_rate(weekly_exit_rates)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "exit_rate_spike"

    # AC-01: 閾値以下ではアラートなし
    def test_離脱率が閾値以下でアラートなし(self) -> None:
        """今週の離脱率が閾値以下ならアラートは生成されない。"""
        gen = AlertGenerator()
        weekly_exit_rates = [0.10, 0.12, 0.08, 0.10, 0.12]  # 今週 0.12 < 0.15
        alerts = gen.check_exit_rate(weekly_exit_rates)
        assert len(alerts) == 0


class TestPushySalesAlert:
    """AC-02: 押し売り感タグが前4週平均×2.0超でアラートが生成される。"""

    # AC-02: 閾値超過でアラート生成
    def test_押し売り感タグが閾値超過でアラート生成(self) -> None:
        """今週の件数が前4週平均×2.0 を超えるとアラートが生成される。"""
        gen = AlertGenerator()
        weekly_counts = [2, 3, 2, 1, 9]  # 平均 2.0 → 閾値 4.0、今週 9 > 4.0
        alerts = gen.check_pushy_sales_tag(weekly_counts)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "pushy_sales_spike"

    # AC-02: 閾値以下ではアラートなし
    def test_押し売り感タグが閾値以下でアラートなし(self) -> None:
        """今週の件数が閾値以下ならアラートは生成されない。"""
        gen = AlertGenerator()
        weekly_counts = [2, 3, 2, 1, 3]  # 今週 3 < 4.0
        alerts = gen.check_pushy_sales_tag(weekly_counts)
        assert len(alerts) == 0


class TestStockShortageAlert:
    """AC-03: 欠品不満が3週連続増加でアラートが生成される。"""

    # AC-03: 3週連続増加でアラート生成
    def test_3週連続増加でアラート生成(self) -> None:
        """直近3週が単調増加でアラートが生成される。"""
        gen = AlertGenerator()
        weekly_counts = [3, 4, 5, 7]  # 4→5→7 で3週連続増加
        alerts = gen.check_stock_shortage_trend(weekly_counts)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "stock_shortage_continuous"

    # AC-03: 連続増加でなければアラートなし
    def test_連続増加でなければアラートなし(self) -> None:
        """途中で減少があればアラートは生成されない。"""
        gen = AlertGenerator()
        weekly_counts = [3, 5, 4, 6]  # 5→4 で途切れる
        alerts = gen.check_stock_shortage_trend(weekly_counts)
        assert len(alerts) == 0


class TestRevisitIntentAlert:
    """AC-04: 再来店意向が2週連続0.3pt以上低下でアラートが生成される。"""

    # AC-04: 2週連続低下でアラート生成
    def test_2週連続低下でアラート生成(self) -> None:
        """直近2週で各0.3pt以上低下するとアラートが生成される。"""
        gen = AlertGenerator()
        weekly_scores = [4.0, 3.6, 3.2]  # 4.0→3.6(-0.4), 3.6→3.2(-0.4)
        alerts = gen.check_revisit_intent_decline(weekly_scores)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "revisit_intent_decline"

    # AC-04: 1週のみの低下ではアラートなし
    def test_1週のみの低下ではアラートなし(self) -> None:
        """1週だけの低下ではアラートは生成されない。"""
        gen = AlertGenerator()
        weekly_scores = [4.0, 3.6, 3.5]  # 3.6→3.5(-0.1) は 0.3 未満
        alerts = gen.check_revisit_intent_decline(weekly_scores)
        assert len(alerts) == 0


class TestAlertContent:
    """AC-05: アラートには異常検知と確認すべき観点がセットで含まれる。"""

    # AC-05: Alert に detection と guidance が含まれる
    def test_アラートに検知内容と確認観点が含まれる(self) -> None:
        """Alert に detection と guidance フィールドが存在する。"""
        gen = AlertGenerator()
        weekly_exit_rates = [0.10, 0.12, 0.08, 0.10, 0.20]
        alerts = gen.check_exit_rate(weekly_exit_rates)
        assert len(alerts) == 1
        alert = alerts[0]
        assert len(alert.detection) > 0
        assert len(alert.guidance) > 0
