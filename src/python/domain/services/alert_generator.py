"""アラート生成バッチ。

設計書 §7.1 に基づく 4 種のアラート閾値判定を行う。

入力: 週次の各指標データ（離脱率、タグ件数、欠品不満件数、再来店意向スコア）
出力: Alert リスト
制約:
    - 接客後離脱率上昇: 前4週平均 × 1.5
    - 押し売り感タグ急増: 前4週平均 × 2.0
    - 欠品不満継続: 3週連続増加
    - 再来店意向低下: 2週連続 0.3pt 以上低下
    - アラートには異常検知と確認すべき観点をセットで含む

Note:
    週次データは時系列順（古い→新しい）のリストで渡される。
    最後の要素が今週分。
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    """アラートデータ。

    Args:
        alert_type: アラート種別識別子
        detection: 異常検知の説明
        guidance: 確認すべき観点・推奨アクション
    """

    alert_type: str
    detection: str
    guidance: str


class AlertGenerator:
    """アラート生成器。4 種の閾値判定を行う。"""

    def check_exit_rate(self, weekly_exit_rates: list[float]) -> list[Alert]:
        """接客後離脱率の異常を判定する。

        Args:
            weekly_exit_rates: 週次離脱率の時系列（古い→新しい、最低 5 週分）

        Returns:
            アラートリスト（0 または 1 件）

        Note:
            閾値: 前4週平均 × 1.5
        """
        if len(weekly_exit_rates) < 5:
            return []

        prev_4_weeks = weekly_exit_rates[-5:-1]
        current_week = weekly_exit_rates[-1]
        avg = sum(prev_4_weeks) / len(prev_4_weeks)
        threshold = avg * 1.5

        if current_week > threshold:
            return [
                Alert(
                    alert_type="exit_rate_spike",
                    detection=(
                        f"接客後離脱率が急上昇: 今週 {current_week:.1%}"
                        f"（前4週平均 {avg:.1%} の {current_week / avg:.1f} 倍）"
                    ),
                    guidance=(
                        "離脱理由の内訳（不安点タグ）を確認し、"
                        "特定の商品カテゴリや時間帯に偏りがないか分析してください"
                    ),
                )
            ]
        return []

    def check_pushy_sales_tag(self, weekly_counts: list[int]) -> list[Alert]:
        """押し売り感タグの急増を判定する。

        Args:
            weekly_counts: 週次の押し売り感タグ件数（古い→新しい、最低 5 週分）

        Returns:
            アラートリスト（0 または 1 件）

        Note:
            閾値: 前4週平均 × 2.0
        """
        if len(weekly_counts) < 5:
            return []

        prev_4_weeks = weekly_counts[-5:-1]
        current_week = weekly_counts[-1]
        avg = sum(prev_4_weeks) / len(prev_4_weeks)
        threshold = avg * 2.0

        if avg > 0 and current_week > threshold:
            return [
                Alert(
                    alert_type="pushy_sales_spike",
                    detection=(
                        f"「押し売り感」タグが急増: 今週 {current_week} 件"
                        f"（前4週平均 {avg:.1f} 件の {current_week / avg:.1f} 倍）"
                    ),
                    guidance=(
                        "該当する接客の具体的なコメント内容を確認し、"
                        "提案前の顧客意向確認が行われているか振り返ってください"
                    ),
                )
            ]
        return []

    def check_stock_shortage_trend(self, weekly_counts: list[int]) -> list[Alert]:
        """欠品不満の継続増加を判定する。

        Args:
            weekly_counts: 週次の欠品不満件数（古い→新しい、最低 4 週分）

        Returns:
            アラートリスト（0 または 1 件）

        Note:
            閾値: 3週連続増加
        """
        if len(weekly_counts) < 4:
            return []

        # 直近 3 週の差分が全て正（単調増加）
        last_4 = weekly_counts[-4:]
        diffs = [last_4[i + 1] - last_4[i] for i in range(3)]

        if all(d > 0 for d in diffs):
            return [
                Alert(
                    alert_type="stock_shortage_continuous",
                    detection=(
                        f"欠品不満が3週連続増加: "
                        f"{last_4[-3]}→{last_4[-2]}→{last_4[-1]} 件"
                    ),
                    guidance=(
                        "欠品が多い商品カテゴリを特定し、"
                        "在庫補充計画と代替提案フローを見直してください"
                    ),
                )
            ]
        return []

    def check_revisit_intent_decline(self, weekly_scores: list[float]) -> list[Alert]:
        """再来店意向スコアの連続低下を判定する。

        Args:
            weekly_scores: 週次の再来店意向平均スコア（古い→新しい、最低 3 週分）

        Returns:
            アラートリスト（0 または 1 件）

        Note:
            閾値: 2週連続 0.3pt 以上低下
        """
        if len(weekly_scores) < 3:
            return []

        last_3 = weekly_scores[-3:]
        decline_1 = last_3[0] - last_3[1]
        decline_2 = last_3[1] - last_3[2]

        if decline_1 >= 0.3 and decline_2 >= 0.3:
            total_decline = last_3[0] - last_3[2]
            return [
                Alert(
                    alert_type="revisit_intent_decline",
                    detection=(
                        f"再来店意向が2週連続低下: "
                        f"{last_3[0]:.1f}→{last_3[1]:.1f}→{last_3[2]:.1f}"
                        f"（合計 -{total_decline:.1f}pt）"
                    ),
                    guidance=(
                        "アンケートの自由記述コメントを確認し、"
                        "接客品質に関する具体的な不満要因を特定してください"
                    ),
                )
            ]
        return []

    def run_all_checks(
        self,
        weekly_exit_rates: list[float],
        weekly_pushy_counts: list[int],
        weekly_shortage_counts: list[int],
        weekly_revisit_scores: list[float],
    ) -> list[Alert]:
        """全4種のアラート判定を実行する。

        Args:
            weekly_exit_rates: 週次離脱率
            weekly_pushy_counts: 週次押し売り感タグ件数
            weekly_shortage_counts: 週次欠品不満件数
            weekly_revisit_scores: 週次再来店意向平均スコア

        Returns:
            生成されたアラートのリスト
        """
        alerts: list[Alert] = []
        alerts.extend(self.check_exit_rate(weekly_exit_rates))
        alerts.extend(self.check_pushy_sales_tag(weekly_pushy_counts))
        alerts.extend(self.check_stock_shortage_trend(weekly_shortage_counts))
        alerts.extend(self.check_revisit_intent_decline(weekly_revisit_scores))

        logger.info("アラート判定完了: %d 件のアラートを生成", len(alerts))
        return alerts
