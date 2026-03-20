"""AI 解釈スキーマ・プロンプトのユニットテスト。

対象: src/python/interpretation/schemas.py, src/python/interpretation/prompts.py
テスト観点: スキーマの設計書準拠、needs_review 判定、プロンプトバージョン管理

Note:
    実際の API 呼び出しは行わない。
"""

import json

import pytest
from pydantic import ValidationError

from src.python.interpretation.schemas import (
    SubjectiveHints,
    TrustInterpretation,
)


class TestTrustInterpretationSchema:
    """AC-01: TrustInterpretation が設計書 §3.3 のスキーマと完全に一致する。"""

    # AC-01: 正常な入力でインスタンスが生成できる
    def test_正常な入力でインスタンスが生成できる(self) -> None:
        """設計書 §3.3 のスキーマに一致する JSON で生成可能。"""
        data = {
            "trust_dimension": "service",
            "sentiment": "positive",
            "severity": 1,
            "theme_tags": ["丁寧な接客"],
            "summary": "丁寧な接客だった",
            "interpretation": "安心感を得たと推定される",
            "subjective_hints": {
                "trait_signal": "対面相談を重視する傾向",
                "state_signal": None,
                "meta_signal": None,
            },
            "confidence": 0.85,
        }
        result = TrustInterpretation.model_validate(data)
        assert result.trust_dimension == "service"
        assert result.sentiment == "positive"
        assert result.severity == 1
        assert result.theme_tags == ["丁寧な接客"]
        assert result.confidence == 0.85

    # AC-01: 5次元すべてが受け入れられる
    @pytest.mark.parametrize(
        "dimension",
        ["service", "product", "proposal", "operation", "story"],
    )
    def test_5次元すべてが有効(self, dimension: str) -> None:
        """trust_dimension の 5 値がすべてバリデーションを通過する。"""
        result = TrustInterpretation(
            trust_dimension=dimension,  # type: ignore[arg-type]
            sentiment="neutral",
            severity=1,
            theme_tags=[],
            summary="テスト",
            interpretation="テスト解釈",
            confidence=0.8,
        )
        assert result.trust_dimension == dimension

    # AC-01: 不正な trust_dimension は拒否される
    def test_不正なdimensionはバリデーションエラー(self) -> None:
        """trust_dimension に未知の値を指定するとエラーになる。"""
        with pytest.raises(ValidationError):
            TrustInterpretation(
                trust_dimension="unknown",  # type: ignore[arg-type]
                sentiment="neutral",
                severity=1,
                theme_tags=[],
                summary="テスト",
                interpretation="テスト解釈",
                confidence=0.8,
            )

    # AC-01: severity は 1, 2, 3 のみ
    def test_severityの範囲外はバリデーションエラー(self) -> None:
        """severity に 0 や 4 を指定するとエラーになる。"""
        with pytest.raises(ValidationError):
            TrustInterpretation(
                trust_dimension="service",
                sentiment="neutral",
                severity=0,  # type: ignore[arg-type]
                theme_tags=[],
                summary="テスト",
                interpretation="テスト解釈",
                confidence=0.8,
            )

    # AC-01: confidence の範囲（0.0〜1.0）
    def test_confidenceの範囲外はバリデーションエラー(self) -> None:
        """confidence に 1.1 や -0.1 を指定するとエラーになる。"""
        with pytest.raises(ValidationError):
            TrustInterpretation(
                trust_dimension="service",
                sentiment="neutral",
                severity=1,
                theme_tags=[],
                summary="テスト",
                interpretation="テスト解釈",
                confidence=1.1,
            )

    # AC-01: JSON からの逆シリアライズが正しく動作する
    def test_JSONからの逆シリアライズが正しく動作する(self) -> None:
        """model_validate_json で JSON 文字列から TrustInterpretation を生成できる。"""
        json_str = json.dumps({
            "trust_dimension": "product",
            "sentiment": "negative",
            "severity": 2,
            "theme_tags": ["品質不満"],
            "summary": "品質が期待以下だった",
            "interpretation": "事前説明との乖離により不満を感じたと推定される",
            "subjective_hints": {"trait_signal": "品質重視", "state_signal": None, "meta_signal": None},
            "confidence": 0.72,
        })
        result = TrustInterpretation.model_validate_json(json_str)
        assert result.trust_dimension == "product"
        assert result.confidence == 0.72


class TestNeedsReview:
    """AC-02: confidence < 0.6 のとき needs_review = True になる。"""

    # AC-02: confidence = 0.59 → needs_review = True
    def test_低confidence_はレビューが必要(self) -> None:
        """confidence < 0.6 で needs_review が True になる。"""
        result = TrustInterpretation(
            trust_dimension="service",
            sentiment="neutral",
            severity=1,
            theme_tags=[],
            summary="テスト",
            interpretation="テスト解釈",
            confidence=0.59,
        )
        assert result.needs_review is True

    # AC-02: confidence = 0.6 → needs_review = False
    def test_境界値0_6はレビュー不要(self) -> None:
        """confidence = 0.6 で needs_review が False になる。"""
        result = TrustInterpretation(
            trust_dimension="service",
            sentiment="neutral",
            severity=1,
            theme_tags=[],
            summary="テスト",
            interpretation="テスト解釈",
            confidence=0.6,
        )
        assert result.needs_review is False

    # AC-02: confidence = 0.85 → needs_review = False
    def test_高confidenceはレビュー不要(self) -> None:
        """confidence >= 0.6 で needs_review が False になる。"""
        result = TrustInterpretation(
            trust_dimension="service",
            sentiment="positive",
            severity=1,
            theme_tags=["丁寧"],
            summary="良い接客",
            interpretation="安心感を得た",
            confidence=0.85,
        )
        assert result.needs_review is False


class TestPromptVersion:
    """AC-03: PROMPT_VERSION 定数でプロンプトのバージョンが管理されている。"""

    # AC-03: PROMPT_VERSION が定義されている
    def test_PROMPT_VERSIONが定義されている(self) -> None:
        """prompts.py に PROMPT_VERSION 定数が存在する。"""
        from src.python.interpretation.prompts import PROMPT_VERSION
        assert isinstance(PROMPT_VERSION, str)
        assert len(PROMPT_VERSION) > 0

    # AC-03: プロンプトテンプレートが存在する
    def test_プロンプトテンプレートが定義されている(self) -> None:
        """prompts.py にプロンプト生成関数が存在し、文字列を返す。"""
        from src.python.interpretation.prompts import build_interpretation_prompt
        prompt = build_interpretation_prompt("テスト入力テキスト")
        assert isinstance(prompt, str)
        assert "テスト入力テキスト" in prompt

    # AC-03: プロンプトに出力スキーマの説明が含まれる
    def test_プロンプトに出力スキーマが含まれる(self) -> None:
        """プロンプトに trust_dimension 等のフィールド説明が含まれる。"""
        from src.python.interpretation.prompts import build_interpretation_prompt
        prompt = build_interpretation_prompt("テスト")
        assert "trust_dimension" in prompt
        assert "confidence" in prompt
        assert "subjective_hints" in prompt
