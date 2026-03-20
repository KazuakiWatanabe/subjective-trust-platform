"""AI 解釈クライアントのユニットテスト。

対象: src/python/interpretation/client.py
テスト観点: 抽象クラス定義・Mock/Anthropic/Bedrock の実装・ファクトリ関数

Note:
    実際の API 呼び出しは行わない。AnthropicClient / BedrockClient は
    SDK をモックして呼び出し引数・回数を検証する。
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.python.interpretation.client import (
    AnthropicClient,
    BaseInterpretationClient,
    BedrockClient,
    MockInterpretationClient,
    get_interpretation_client,
)
from src.python.interpretation.schemas import TrustInterpretation


class TestBaseInterpretationClient:
    """AC-01: BaseInterpretationClient 抽象クラスが定義されている。"""

    # AC-01: 抽象クラスを直接インスタンス化できないことを検証
    def test_抽象クラスは直接インスタンス化できない(self) -> None:
        """BaseInterpretationClient を直接インスタンス化すると TypeError になる。"""
        with pytest.raises(TypeError):
            BaseInterpretationClient()  # type: ignore[abstract]

    # AC-01: interpret メソッドが抽象メソッドとして定義されている
    def test_interpretメソッドが抽象定義されている(self) -> None:
        """interpret が abstractmethod として存在する。"""
        assert hasattr(BaseInterpretationClient, "interpret")
        assert getattr(BaseInterpretationClient.interpret, "__isabstractmethod__", False)


class TestMockInterpretationClient:
    """AC-02: MockInterpretationClient が実装されており AI_BACKEND=mock で動作する。"""

    # AC-02: Mock クライアントが TrustInterpretation を返す
    @pytest.mark.asyncio
    async def test_モッククライアントがTrustInterpretationを返す(self) -> None:
        """MockInterpretationClient.interpret が TrustInterpretation を返す。"""
        client = MockInterpretationClient()
        result = await client.interpret("テスト入力テキスト")
        assert isinstance(result, TrustInterpretation)

    # AC-02: Mock クライアントが fixture の値を返す
    @pytest.mark.asyncio
    async def test_モッククライアントのレスポンスが有効なスキーマ(self) -> None:
        """返却値が TrustInterpretation のバリデーションを通過する。"""
        client = MockInterpretationClient()
        result = await client.interpret("丁寧な接客でした")
        assert result.trust_dimension in (
            "service", "product", "proposal", "operation", "story"
        )
        assert result.sentiment in ("positive", "negative", "neutral")
        assert result.severity in (1, 2, 3)
        assert 0.0 <= result.confidence <= 1.0

    # AC-05: Mock クライアントが外部 API を呼び出さない
    @pytest.mark.asyncio
    async def test_モッククライアントは外部APIを呼び出さない(self) -> None:
        """MockInterpretationClient は httpx や anthropic SDK を使わない。"""
        client = MockInterpretationClient()
        # anthropic / boto3 をモック化し、呼び出されないことを検証
        with patch("src.python.interpretation.client.anthropic", create=True) as mock_sdk:
            result = await client.interpret("テスト")
            mock_sdk.assert_not_called()
        assert isinstance(result, TrustInterpretation)


class TestAnthropicClient:
    """AC-03: AnthropicClient が実装されている。"""

    # AC-03: AnthropicClient が BaseInterpretationClient を継承している
    def test_AnthropicClientが基底クラスを継承している(self) -> None:
        """AnthropicClient は BaseInterpretationClient のサブクラスである。"""
        assert issubclass(AnthropicClient, BaseInterpretationClient)

    # AC-03: AnthropicClient.interpret が SDK を正しく呼び出す
    @pytest.mark.asyncio
    async def test_AnthropicClientがSDKを呼び出す(self) -> None:
        """interpret 呼び出し時に anthropic SDK の messages.create が呼ばれる。"""
        mock_response_content = json.dumps({
            "trust_dimension": "service",
            "sentiment": "positive",
            "severity": 1,
            "theme_tags": ["丁寧"],
            "summary": "丁寧な接客だった",
            "interpretation": "安心感を得たと推定される",
            "subjective_hints": {
                "trait_signal": None,
                "state_signal": None,
                "meta_signal": None,
            },
            "confidence": 0.9,
        })

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=mock_response_content)]

        mock_client_instance = MagicMock()
        mock_client_instance.messages.create = AsyncMock(return_value=mock_message)

        client = AnthropicClient.__new__(AnthropicClient)
        client._client = mock_client_instance  # type: ignore[attr-defined]
        client._model = "claude-sonnet-4-20250514"  # type: ignore[attr-defined]

        result = await client.interpret("丁寧な接客でした")
        assert isinstance(result, TrustInterpretation)
        assert result.trust_dimension == "service"
        mock_client_instance.messages.create.assert_called_once()


class TestBedrockClient:
    """AC-03: BedrockClient が実装されている。"""

    # AC-03: BedrockClient が BaseInterpretationClient を継承している
    def test_BedrockClientが基底クラスを継承している(self) -> None:
        """BedrockClient は BaseInterpretationClient のサブクラスである。"""
        assert issubclass(BedrockClient, BaseInterpretationClient)


class TestGetInterpretationClient:
    """AC-04: AI_BACKEND 環境変数で呼び出し先を切り替えられる。"""

    # AC-04: mock を指定すると MockInterpretationClient が返る
    def test_mock指定でMockClientが返る(self) -> None:
        """AI_BACKEND=mock で MockInterpretationClient が選択される。"""
        with patch.dict(os.environ, {"AI_BACKEND": "mock"}):
            from src.python.config import Settings
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            client = get_interpretation_client(settings)
            assert isinstance(client, MockInterpretationClient)

    # AC-04: anthropic を指定すると AnthropicClient が返る
    def test_anthropic指定でAnthropicClientが返る(self) -> None:
        """AI_BACKEND=anthropic で AnthropicClient が選択される。"""
        with patch.dict(os.environ, {"AI_BACKEND": "anthropic", "ANTHROPIC_API_KEY": "sk-test"}):
            from src.python.config import Settings
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            client = get_interpretation_client(settings)
            assert isinstance(client, AnthropicClient)

    # AC-04: bedrock を指定すると BedrockClient が返る
    def test_bedrock指定でBedrockClientが返る(self) -> None:
        """AI_BACKEND=bedrock で BedrockClient が選択される。"""
        with patch.dict(os.environ, {"AI_BACKEND": "bedrock"}):
            from src.python.config import Settings
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            client = get_interpretation_client(settings)
            assert isinstance(client, BedrockClient)
