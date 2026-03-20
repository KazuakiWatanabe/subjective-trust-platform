"""AI 解釈出力スキーマ。

設計書 §3.3 に基づく AI 解釈結果の構造体。
このスキーマは変更禁止。

Note:
    confidence < 0.6 の場合は needs_review = True を自動セットする。
    subjective_hints は Phase 2 で SubjectiveProfile 構築に活用する。
"""

from typing import Literal

from pydantic import BaseModel, Field


class SubjectiveHints(BaseModel):
    """主観手がかり。Trait / State / Meta の 3 層シグナル。"""

    trait_signal: str | None = None
    state_signal: str | None = None
    meta_signal: str | None = None


class TrustInterpretation(BaseModel):
    """AI 解釈出力スキーマ（変更禁止）。

    Args:
        trust_dimension: 信頼の 5 次元のいずれか
        sentiment: 感情極性
        severity: 深刻度（1〜3）
        theme_tags: テーマタグ（AI 分類または手動）
        summary: 1 文の要約
        interpretation: 「なぜそう感じたか」の 1 文解釈
        subjective_hints: Trait / State / Meta 手がかり
        confidence: AI 分類の確信度（0.0〜1.0）
    """

    trust_dimension: Literal["service", "product", "proposal", "operation", "story"]
    sentiment: Literal["positive", "negative", "neutral"]
    severity: Literal[1, 2, 3]
    theme_tags: list[str]
    summary: str
    interpretation: str
    subjective_hints: SubjectiveHints = Field(default_factory=SubjectiveHints)
    confidence: float = Field(ge=0.0, le=1.0)

    @property
    def needs_review(self) -> bool:
        """confidence < 0.6 の場合は人間レビューが必要。"""
        return self.confidence < 0.6
