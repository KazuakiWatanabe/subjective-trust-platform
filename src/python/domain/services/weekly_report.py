"""週次レポート自動生成。

設計書 §6.3 に基づく接客改善レポートの生成ロジック。
毎週月曜朝に店長向けに配信する内容を構成する。

入力: TrustEvent リスト、Visit リスト
出力: WeeklyReportData
制約:
    - 不満テーマ上位 3 件
    - 高評価接客の共通パターン
    - 欠品対応の代替提案実施率
    - AI 改善アクション提案（最大 3 件）

Note:
    Phase 1 では改善提案はルールベースのテンプレートで生成する。
    Phase 2 以降で AI 生成に移行予定。
    Slack / メール配信は本モジュールの対象外。
"""

import logging
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# 不満テーマに基づく改善提案テンプレート
_SUGGESTION_TEMPLATES: dict[str, str] = {
    "押し売り感": "提案前に顧客の意向（下見・購入目的）を確認するステップを徹底する",
    "説明不足": "商品説明時に素材・サイズ・利用シーンの3点を必ずカバーする",
    "欠品不満": "欠品発生時は代替提案と取り寄せ案内を必ず行い、記録する",
    "待ち時間": "混雑時の声掛け（お待たせ案内）と優先対応フローを見直す",
    "品質不満": "品質に関する顧客の期待値を事前にヒアリングし、適切な商品を提案する",
    "対応不備": "問い合わせ・クレーム対応のエスカレーションフローを再確認する",
}


@dataclass
class WeeklyReportData:
    """週次レポートの構成データ。

    Args:
        store_id: 対象店舗 ID
        report_date: レポート対象日
        top_complaint_themes: 不満テーマ上位（テーマ名, 件数）
        high_rated_patterns: 高評価パターン（テーマ名, 件数）
        alternative_proposal_rate: 欠品対応の代替提案実施率（0.0〜1.0、None=欠品なし）
        improvement_suggestions: AI 改善アクション提案（最大 3 件）
    """

    store_id: uuid.UUID
    report_date: date
    top_complaint_themes: list[tuple[str, int]]
    high_rated_patterns: list[tuple[str, int]]
    alternative_proposal_rate: float | None
    improvement_suggestions: list[str]


class WeeklyReportGenerator:
    """週次レポート生成器。"""

    def extract_top_complaint_themes(
        self,
        events: list[dict[str, Any]],
        top_n: int = 3,
    ) -> list[tuple[str, int]]:
        """不満テーマ上位 N 件を抽出する。

        Args:
            events: TrustEvent 辞書リスト
            top_n: 抽出件数

        Returns:
            (テーマ名, 件数) のリスト（頻度降順）
        """
        counter: Counter[str] = Counter()
        for event in events:
            if event.get("sentiment") != "negative":
                continue
            for tag in event.get("theme_tags", []):
                counter[tag] += 1
        return counter.most_common(top_n)

    def extract_high_rated_patterns(
        self,
        events: list[dict[str, Any]],
        top_n: int = 3,
    ) -> list[tuple[str, int]]:
        """高評価接客の共通パターンを抽出する。

        Args:
            events: TrustEvent 辞書リスト
            top_n: 抽出件数

        Returns:
            (テーマ名, 件数) のリスト（頻度降順）
        """
        counter: Counter[str] = Counter()
        for event in events:
            if event.get("sentiment") != "positive":
                continue
            for tag in event.get("theme_tags", []):
                counter[tag] += 1
        return counter.most_common(top_n)

    def calculate_alternative_proposal_rate(
        self,
        visits: list[dict[str, Any]],
    ) -> float | None:
        """欠品対応の代替提案実施率を算出する。

        Args:
            visits: Visit 辞書リスト

        Returns:
            0.0〜1.0 の実施率。欠品離脱がない場合は None。
        """
        out_of_stock_visits = [
            v for v in visits
            if v.get("contact_result") == "out_of_stock_exit"
        ]
        if not out_of_stock_visits:
            return None

        proposed_count = sum(
            1 for v in out_of_stock_visits
            if v.get("alternative_proposed") is True
        )
        return proposed_count / len(out_of_stock_visits)

    def generate_suggestions(
        self,
        top_themes: list[tuple[str, int]],
        max_suggestions: int = 3,
    ) -> list[str]:
        """不満テーマに基づく改善アクション提案を生成する。

        Args:
            top_themes: 不満テーマ上位（テーマ名, 件数）
            max_suggestions: 最大提案件数

        Returns:
            改善提案文のリスト（最大 max_suggestions 件）

        Note:
            Phase 1 ではテンプレートベース。Phase 2 以降で AI 生成に移行予定。
        """
        suggestions: list[str] = []
        for theme_name, count in top_themes:
            if len(suggestions) >= max_suggestions:
                break
            template = _SUGGESTION_TEMPLATES.get(theme_name)
            if template:
                suggestions.append(f"【{theme_name}（{count}件）】{template}")
            else:
                suggestions.append(
                    f"【{theme_name}（{count}件）】該当テーマの具体事例を確認し、改善施策を検討する"
                )
        return suggestions

    def generate_report(
        self,
        store_id: uuid.UUID,
        events: list[dict[str, Any]],
        visits: list[dict[str, Any]],
    ) -> WeeklyReportData:
        """週次レポートデータを生成する。

        Args:
            store_id: 対象店舗 ID
            events: 今週の TrustEvent 辞書リスト
            visits: 今週の Visit 辞書リスト

        Returns:
            WeeklyReportData
        """
        top_themes = self.extract_top_complaint_themes(events)
        high_rated = self.extract_high_rated_patterns(events)
        alt_rate = self.calculate_alternative_proposal_rate(visits)
        suggestions = self.generate_suggestions(top_themes)

        report = WeeklyReportData(
            store_id=store_id,
            report_date=date.today(),
            top_complaint_themes=top_themes,
            high_rated_patterns=high_rated,
            alternative_proposal_rate=alt_rate,
            improvement_suggestions=suggestions,
        )

        logger.info(
            "週次レポート生成: store_id=%s, 不満テーマ %d 件, 改善提案 %d 件",
            store_id,
            len(top_themes),
            len(suggestions),
        )
        return report
