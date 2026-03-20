"""重みテーブル定義。

設計書 §2.4 に基づく信頼スコア算出用の重みテーブルと recency_decay を定義する。
重みテーブルは四半期ごとにレビュー・調整する前提の外部変更可能な構造とする。

入力: イベント種別・経過週数
出力: 基本重み・recency_decay 値
制約:
    - 5 次元すべてに重みテーブルを定義する
    - recency_decay は 4 段階（1.0 / 0.7 / 0.4 / 0.1）

Note:
    初期値は定性判断で設定。再来店率・NPS 等の外部指標との相関分析で調整する。
"""
# TODO(phase2): C# 移管予定 — 重みテーブルは C# ドメインサービスに移行する

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class WeightConfig:
    """イベント種別ごとの重み設定。

    Args:
        event_type: イベント種別識別子
        direction: 信頼への影響方向（positive=形成 / negative=毀損）
        base_weight: 基本重み（正の値）。negative の場合は算出時に減算される
        description: 人間向けの説明（四半期レビュー時の参照用）
    """

    event_type: str
    direction: Literal["positive", "negative"]
    base_weight: float
    description: str = ""


# --- recency_decay 定義 ---

RECENCY_DECAY: list[tuple[int, int, float]] = [
    (1, 4, 1.0),    # 直近 4 週
    (5, 8, 0.7),    # 5〜8 週
    (9, 12, 0.4),   # 9〜12 週
    (13, 9999, 0.1),  # それ以前
]


def get_recency_decay(weeks_ago: int) -> float:
    """経過週数に応じた recency_decay 値を返す。

    Args:
        weeks_ago: イベントからの経過週数（1 以上）

    Returns:
        recency_decay 値
    """
    for start, end, decay in RECENCY_DECAY:
        if start <= weeks_ago <= end:
            return decay
    return 0.1


# --- 5 次元の重みテーブル ---

DIMENSION_WEIGHTS: dict[str, list[WeightConfig]] = {
    "service": [
        WeightConfig("questionnaire_high", "positive", 2.0, "アンケート高評価（4-5点）"),
        WeightConfig("questionnaire_low", "negative", 3.0, "アンケート低評価（1-2点）。毀損は形成より影響大"),
        WeightConfig("purchase_after_contact", "positive", 1.0, "接客後購買"),
        WeightConfig("exit_after_contact", "negative", 1.5, "接客後離脱"),
        WeightConfig("pushy_comment", "negative", 4.0, "「押し売り」分類コメント。重度の信頼毀損"),
        WeightConfig("polite_comment", "positive", 2.5, "「丁寧」分類コメント"),
        WeightConfig("complaint_service", "negative", 5.0, "クレーム（接客起因）"),
    ],
    "product": [
        WeightConfig("questionnaire_high", "positive", 2.0, "アンケート高評価（商品関連）"),
        WeightConfig("questionnaire_low", "negative", 3.0, "アンケート低評価（商品関連）"),
        WeightConfig("return_product", "negative", 4.0, "商品返品"),
        WeightConfig("quality_complaint", "negative", 3.5, "品質不満コメント"),
        WeightConfig("quality_praise", "positive", 2.5, "品質称賛コメント"),
        WeightConfig("purchase_repeat_category", "positive", 1.5, "同一カテゴリ再購入"),
    ],
    "proposal": [
        WeightConfig("questionnaire_high", "positive", 2.0, "アンケート高評価（提案関連）"),
        WeightConfig("questionnaire_low", "negative", 3.0, "アンケート低評価（提案関連）"),
        WeightConfig("out_of_stock_no_alternative", "negative", 3.5, "欠品離脱・代替提案なし"),
        WeightConfig("out_of_stock_with_alternative", "positive", 1.0, "欠品時に代替提案あり"),
        WeightConfig("mismatch_comment", "negative", 3.0, "「合わない提案」分類コメント"),
        WeightConfig("good_suggestion_comment", "positive", 2.5, "「良い提案」分類コメント"),
    ],
    "operation": [
        WeightConfig("questionnaire_high", "positive", 1.5, "アンケート高評価（運営関連）"),
        WeightConfig("questionnaire_low", "negative", 2.5, "アンケート低評価（運営関連）"),
        WeightConfig("stock_shortage_complaint", "negative", 3.0, "欠品不満コメント"),
        WeightConfig("smooth_operation_comment", "positive", 2.0, "スムーズな運営コメント"),
        WeightConfig("wait_time_complaint", "negative", 2.5, "待ち時間不満"),
        WeightConfig("delivery_issue", "negative", 3.5, "受取・配送トラブル"),
    ],
    "story": [
        WeightConfig("questionnaire_high", "positive", 1.5, "アンケート高評価（ブランド関連）"),
        WeightConfig("questionnaire_low", "negative", 2.5, "アンケート低評価（ブランド関連）"),
        WeightConfig("brand_consistency_praise", "positive", 3.0, "ブランド一貫性の称賛"),
        WeightConfig("brand_inconsistency", "negative", 3.5, "ブランドらしくないとの指摘"),
        WeightConfig("story_resonance", "positive", 2.5, "世界観への共感コメント"),
        WeightConfig("external_review_positive", "positive", 1.5, "外部レビュー高評価"),
        WeightConfig("external_review_negative", "negative", 2.0, "外部レビュー低評価"),
    ],
}


# --- 総合スコアの次元重み（デフォルト均等） ---

OVERALL_DIMENSION_WEIGHTS: dict[str, float] = {
    "service": 0.2,
    "product": 0.2,
    "proposal": 0.2,
    "operation": 0.2,
    "story": 0.2,
}


def get_weight_config(dimension: str) -> list[WeightConfig]:
    """指定次元の重み設定リストを返す。

    Args:
        dimension: 信頼の 5 次元のいずれか

    Returns:
        WeightConfig のリスト

    Raises:
        KeyError: 未知の次元が指定された場合
    """
    return DIMENSION_WEIGHTS[dimension]
