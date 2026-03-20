"""週次レポート自動生成のユニットテスト。

対象: src/python/domain/services/weekly_report.py
テスト観点: 不満テーマ抽出、高評価パターン、代替提案率、AI改善提案

Note:
    Slack/メール配信はテスト対象外。レポートデータ生成ロジックのみ検証する。
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.python.domain.services.weekly_report import (
    WeeklyReportGenerator,
    WeeklyReportData,
)


def _make_event(
    dimension: str = "service",
    sentiment: str = "negative",
    theme_tags: list[str] | None = None,
    weeks_ago: int = 0,
) -> dict[str, Any]:
    """テスト用 TrustEvent 辞書。"""
    return {
        "trust_event_id": uuid.uuid4(),
        "store_id": uuid.uuid4(),
        "trust_dimension": dimension,
        "sentiment": sentiment,
        "theme_tags": theme_tags or [],
        "detected_at": datetime.now(timezone.utc) - timedelta(weeks=weeks_ago),
    }


def _make_visit(
    contact_result: str = "purchase",
    alternative_proposed: bool | None = None,
    weeks_ago: int = 0,
) -> dict[str, Any]:
    """テスト用 Visit 辞書。"""
    return {
        "visit_id": uuid.uuid4(),
        "store_id": uuid.uuid4(),
        "contact_result": contact_result,
        "alternative_proposed": alternative_proposed,
        "visit_datetime": datetime.now(timezone.utc) - timedelta(weeks=weeks_ago),
    }


class TestComplaintThemeExtraction:
    """AC-01: 今週増加した不満テーマ上位3件が抽出される。"""

    # AC-01: 不満テーマが頻度順で上位3件に絞られる
    def test_不満テーマ上位3件が抽出される(self) -> None:
        """negative イベントの theme_tags を頻度順で上位 3 件抽出する。"""
        events = [
            _make_event(sentiment="negative", theme_tags=["押し売り感"]),
            _make_event(sentiment="negative", theme_tags=["押し売り感"]),
            _make_event(sentiment="negative", theme_tags=["押し売り感"]),
            _make_event(sentiment="negative", theme_tags=["説明不足"]),
            _make_event(sentiment="negative", theme_tags=["説明不足"]),
            _make_event(sentiment="negative", theme_tags=["欠品不満"]),
            _make_event(sentiment="negative", theme_tags=["待ち時間"]),
        ]
        gen = WeeklyReportGenerator()
        top_themes = gen.extract_top_complaint_themes(events, top_n=3)
        assert len(top_themes) == 3
        assert top_themes[0][0] == "押し売り感"
        assert top_themes[0][1] == 3

    # AC-01: positive イベントは不満テーマに含まれない
    def test_positiveイベントは除外される(self) -> None:
        """positive の theme_tags は不満テーマに含まれない。"""
        events = [
            _make_event(sentiment="positive", theme_tags=["丁寧な接客"]),
            _make_event(sentiment="negative", theme_tags=["押し売り感"]),
        ]
        gen = WeeklyReportGenerator()
        top_themes = gen.extract_top_complaint_themes(events, top_n=3)
        theme_names = [t[0] for t in top_themes]
        assert "丁寧な接客" not in theme_names


class TestHighRatedPatterns:
    """AC-02: 高評価接客の共通パターンが抽出される。"""

    # AC-02: positive イベントの theme_tags が抽出される
    def test_高評価パターンが抽出される(self) -> None:
        """positive イベントの theme_tags を頻度順で抽出する。"""
        events = [
            _make_event(sentiment="positive", theme_tags=["丁寧な接客"]),
            _make_event(sentiment="positive", theme_tags=["丁寧な接客"]),
            _make_event(sentiment="positive", theme_tags=["商品知識"]),
        ]
        gen = WeeklyReportGenerator()
        patterns = gen.extract_high_rated_patterns(events, top_n=3)
        assert len(patterns) >= 1
        assert patterns[0][0] == "丁寧な接客"


class TestAlternativeProposalRate:
    """AC-03: 欠品対応の代替提案実施率の推移が含まれる。"""

    # AC-03: 欠品離脱の中で代替提案実施率を算出する
    def test_代替提案実施率が算出される(self) -> None:
        """欠品離脱 4 件中 2 件で代替提案 → 50%。"""
        visits = [
            _make_visit(contact_result="out_of_stock_exit", alternative_proposed=True),
            _make_visit(contact_result="out_of_stock_exit", alternative_proposed=True),
            _make_visit(contact_result="out_of_stock_exit", alternative_proposed=False),
            _make_visit(contact_result="out_of_stock_exit", alternative_proposed=False),
            _make_visit(contact_result="purchase"),
        ]
        gen = WeeklyReportGenerator()
        rate = gen.calculate_alternative_proposal_rate(visits)
        assert rate == pytest.approx(0.5)

    # AC-03: 欠品離脱がない場合は None を返す
    def test_欠品離脱なしでNone(self) -> None:
        """欠品離脱がなければ代替提案率は算出しない。"""
        visits = [_make_visit(contact_result="purchase")]
        gen = WeeklyReportGenerator()
        rate = gen.calculate_alternative_proposal_rate(visits)
        assert rate is None


class TestImprovementSuggestions:
    """AC-04: AI 生成の改善アクション提案が最大3件含まれる。"""

    # AC-04: 改善提案が最大 3 件返される
    def test_改善提案が最大3件(self) -> None:
        """generate_suggestions が最大 3 件のリストを返す。"""
        gen = WeeklyReportGenerator()
        top_themes = [("押し売り感", 5), ("説明不足", 3), ("欠品不満", 2)]
        suggestions = gen.generate_suggestions(top_themes)
        assert len(suggestions) <= 3
        assert len(suggestions) >= 1

    # AC-04: 不満テーマが空の場合は空リスト
    def test_不満テーマ空で提案も空(self) -> None:
        """不満テーマがなければ改善提案も空。"""
        gen = WeeklyReportGenerator()
        suggestions = gen.generate_suggestions([])
        assert len(suggestions) == 0


class TestWeeklyReportData:
    """AC-05: レポートデータが正しく構成される。"""

    # AC-05: generate_report が WeeklyReportData を返す
    def test_レポートデータが生成される(self) -> None:
        """generate_report が全フィールドを含む WeeklyReportData を返す。"""
        events = [
            _make_event(sentiment="negative", theme_tags=["押し売り感"]),
            _make_event(sentiment="positive", theme_tags=["丁寧な接客"]),
        ]
        visits = [
            _make_visit(contact_result="out_of_stock_exit", alternative_proposed=True),
        ]
        gen = WeeklyReportGenerator()
        report = gen.generate_report(
            store_id=uuid.uuid4(),
            events=events,
            visits=visits,
        )
        assert isinstance(report, WeeklyReportData)
        assert report.top_complaint_themes is not None
        assert report.high_rated_patterns is not None
        assert report.alternative_proposal_rate is not None
        assert report.improvement_suggestions is not None
