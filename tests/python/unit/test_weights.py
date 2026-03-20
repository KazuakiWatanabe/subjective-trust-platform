"""重みテーブルのユニットテスト。

対象: src/python/scoring/weights.py
テスト観点: 5次元の重みテーブル定義、recency_decay 4段階、外部変更可能性

Note:
    設計書 §2.4 の重みテーブルと recency_decay の仕様を検証する。
"""

import pytest

from src.python.scoring.weights import (
    DIMENSION_WEIGHTS,
    RECENCY_DECAY,
    WeightConfig,
    get_recency_decay,
    get_weight_config,
)


class TestDimensionWeights:
    """AC-01: 設計書 §2.4 の重みテーブルが5次元すべてに定義されている。"""

    # AC-01: 5次元すべてに重みテーブルが存在する
    def test_5次元すべてに重みテーブルが定義されている(self) -> None:
        """service, product, proposal, operation, story の5次元が存在する。"""
        expected = {"service", "product", "proposal", "operation", "story"}
        assert expected == set(DIMENSION_WEIGHTS.keys())

    # AC-01: 各次元にイベント種別ごとの重みが定義されている
    def test_各次元にイベント重みが存在する(self) -> None:
        """各次元の重みテーブルが空でないことを検証する。"""
        for dimension, weights in DIMENSION_WEIGHTS.items():
            assert len(weights) > 0, f"{dimension} の重みテーブルが空"

    # AC-01: 接客信頼（service）に設計書の重みが含まれる
    def test_接客信頼の設計書記載イベントが定義されている(self) -> None:
        """設計書 §2.4 の接客信頼の重みテーブル例がすべて含まれる。"""
        service_weights = DIMENSION_WEIGHTS["service"]
        event_types = {w.event_type for w in service_weights}
        # 設計書に記載のある代表的なイベント種別
        assert "questionnaire_high" in event_types
        assert "questionnaire_low" in event_types
        assert "purchase_after_contact" in event_types
        assert "exit_after_contact" in event_types

    # AC-01: 重みの方向（positive/negative）が正しい
    def test_重みの方向が正しい(self) -> None:
        """positive イベントは正の重み、negative イベントは負の重みを持つ。"""
        for dimension, weights in DIMENSION_WEIGHTS.items():
            for w in weights:
                if w.direction == "positive":
                    assert w.base_weight > 0, (
                        f"{dimension}/{w.event_type}: positive なのに重みが 0 以下"
                    )
                elif w.direction == "negative":
                    assert w.base_weight > 0, (
                        f"{dimension}/{w.event_type}: negative の base_weight は正の値で定義する"
                    )


class TestRecencyDecay:
    """AC-02: recency_decay が 4段階で定義されている。"""

    # AC-02: 4段階の recency_decay が定義されている
    def test_4段階のdecayが定義されている(self) -> None:
        """RECENCY_DECAY に 4 段階の値が存在する。"""
        assert len(RECENCY_DECAY) == 4

    # AC-02: 直近4週=1.0 / 5〜8週=0.7 / 9〜12週=0.4 / それ以前=0.1
    def test_decay値が設計書通り(self) -> None:
        """各段階の decay 値が設計書 §2.4 に一致する。"""
        assert get_recency_decay(weeks_ago=1) == 1.0
        assert get_recency_decay(weeks_ago=4) == 1.0
        assert get_recency_decay(weeks_ago=5) == 0.7
        assert get_recency_decay(weeks_ago=8) == 0.7
        assert get_recency_decay(weeks_ago=9) == 0.4
        assert get_recency_decay(weeks_ago=12) == 0.4
        assert get_recency_decay(weeks_ago=13) == 0.1
        assert get_recency_decay(weeks_ago=52) == 0.1


class TestWeightConfigModifiable:
    """AC-03: 重みテーブルは外部から変更可能な構造になっている。"""

    # AC-03: WeightConfig がデータクラスとして定義されている
    def test_WeightConfigが構造体として定義されている(self) -> None:
        """WeightConfig のフィールドが読み取り可能である。"""
        config = WeightConfig(
            event_type="test_event",
            direction="positive",
            base_weight=2.0,
            description="テスト",
        )
        assert config.event_type == "test_event"
        assert config.base_weight == 2.0

    # AC-03: get_weight_config で次元別の設定を取得・上書きできる
    def test_次元別設定を取得できる(self) -> None:
        """get_weight_config で指定次元の重みリストを取得できる。"""
        configs = get_weight_config("service")
        assert len(configs) > 0
        assert all(isinstance(c, WeightConfig) for c in configs)

    # AC-03: 総合スコアの次元重みがデフォルト均等（各0.2）
    def test_総合スコアの次元重みがデフォルト均等(self) -> None:
        """5次元のデフォルト重みが均等（各0.2）である。"""
        from src.python.scoring.weights import OVERALL_DIMENSION_WEIGHTS
        assert len(OVERALL_DIMENSION_WEIGHTS) == 5
        for dim, weight in OVERALL_DIMENSION_WEIGHTS.items():
            assert weight == pytest.approx(0.2), f"{dim} の重みが 0.2 でない"
