"""AI 解釈クライアント抽象・具象実装。

BaseInterpretationClient を基底クラスとし、Mock / Anthropic / Bedrock の
3 種類の具象クライアントを提供する。AI_BACKEND 環境変数で切り替え可能。

Note:
    テストでは MockInterpretationClient を使用し、実 API を呼び出さないこと。
    外部通信先は AGENTS.md の allowlist に限定される。
    - api.anthropic.com（Anthropic Claude API）
    - bedrock-runtime.*.amazonaws.com（Amazon Bedrock）
"""
# TODO(phase2): C# から SQS 経由で呼び出す構成に変更予定

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path

import anthropic
import boto3

from src.python.config import Settings
from src.python.interpretation.schemas import TrustInterpretation

logger = logging.getLogger(__name__)

# モックレスポンス fixture のパス
_MOCK_FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests" / "python" / "fixtures" / "mock_interpretation.json"


class BaseInterpretationClient(ABC):
    """AI 解釈クライアントの抽象基底クラス。

    すべての具象クライアントはこのクラスを継承し、
    interpret メソッドを実装する。
    """

    @abstractmethod
    async def interpret(self, text: str) -> TrustInterpretation:
        """テキストを AI 解釈し、構造化された TrustInterpretation を返す。

        Args:
            text: 解釈対象の自由記述テキスト。
                  個人識別情報はマスキング済みであること。

        Returns:
            TrustInterpretation: AI 解釈結果
        """
        ...


class MockInterpretationClient(BaseInterpretationClient):
    """ローカル開発・テスト用モッククライアント。

    fixtures/mock_interpretation.json からローテーションで固定レスポンスを返す。
    外部 API を一切呼び出さない。
    """

    def __init__(self) -> None:
        self._responses: list[TrustInterpretation] = []
        self._index = 0
        self._load_fixtures()

    def _load_fixtures(self) -> None:
        """fixture ファイルからモックレスポンスを読み込む。"""
        if _MOCK_FIXTURE_PATH.exists():
            with open(_MOCK_FIXTURE_PATH, encoding="utf-8") as f:
                data = json.load(f)
            self._responses = [TrustInterpretation.model_validate(item) for item in data]
        else:
            # fixture がない場合はデフォルトレスポンスを使用
            self._responses = [
                TrustInterpretation(
                    trust_dimension="service",
                    sentiment="neutral",
                    severity=1,
                    theme_tags=["モック"],
                    summary="モックレスポンス",
                    interpretation="テスト用の固定レスポンスです",
                    confidence=0.8,
                )
            ]

    async def interpret(self, text: str) -> TrustInterpretation:
        """固定レスポンスをローテーションで返す。

        Args:
            text: 解釈対象テキスト（モックでは内容を使用しない）

        Returns:
            TrustInterpretation: fixture から読み込んだモックレスポンス
        """
        response = self._responses[self._index % len(self._responses)]
        self._index += 1
        logger.debug("MockInterpretationClient: index=%d, text=%s", self._index, text[:50])
        return response


class AnthropicClient(BaseInterpretationClient):
    """Anthropic Claude API 直接呼び出しクライアント。

    通信先: api.anthropic.com（allowlist 登録済み）
    """

    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def interpret(self, text: str) -> TrustInterpretation:
        """Anthropic Claude API でテキストを解釈する。

        Args:
            text: 解釈対象テキスト（PII マスキング済み）

        Returns:
            TrustInterpretation: AI 解釈結果

        Raises:
            anthropic.APIError: API 呼び出しに失敗した場合
        """
        # プロンプトは T-04 で prompts.py に集約する。暫定で最小限のプロンプトを使用
        message = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "以下のテキストを信頼観測の観点で分析し、JSON で返してください。\n\n"
                        f"テキスト: {text}"
                    ),
                }
            ],
        )
        response_text = message.content[0].text  # type: ignore[union-attr]
        return TrustInterpretation.model_validate_json(response_text)


class BedrockClient(BaseInterpretationClient):
    """AWS Bedrock 経由の Claude API クライアント。

    通信先: bedrock-runtime.*.amazonaws.com（allowlist 登録済み）
    """

    def __init__(self, region: str, model_id: str) -> None:
        self._bedrock = boto3.client(
            "bedrock-runtime",
            region_name=region,
        )
        self._model_id = model_id

    async def interpret(self, text: str) -> TrustInterpretation:
        """Bedrock 経由で Claude API を呼び出しテキストを解釈する。

        Args:
            text: 解釈対象テキスト（PII マスキング済み）

        Returns:
            TrustInterpretation: AI 解釈結果

        Note:
            boto3 は同期クライアントのため、本番では asyncio.to_thread で
            ラップすることを推奨する。T-05 で対応予定。
        """
        import asyncio

        # プロンプトは T-04 で prompts.py に集約する
        request_body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "以下のテキストを信頼観測の観点で分析し、JSON で返してください。\n\n"
                        f"テキスト: {text}"
                    ),
                }
            ],
        })

        # boto3 は同期なので別スレッドで実行
        response = await asyncio.to_thread(
            self._bedrock.invoke_model,
            modelId=self._model_id,
            body=request_body,
            contentType="application/json",
            accept="application/json",
        )

        response_body = json.loads(response["body"].read())
        response_text = response_body["content"][0]["text"]
        return TrustInterpretation.model_validate_json(response_text)


def get_interpretation_client(settings: Settings) -> BaseInterpretationClient:
    """Settings の AI_BACKEND に応じた具象クライアントを返すファクトリ関数。

    Args:
        settings: アプリケーション設定

    Returns:
        BaseInterpretationClient: AI バックエンドに対応するクライアント

    Raises:
        ValueError: 未知の AI_BACKEND が指定された場合
    """
    backend = settings.ai_backend
    if backend == "mock":
        return MockInterpretationClient()
    if backend == "anthropic":
        return AnthropicClient(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )
    if backend == "bedrock":
        return BedrockClient(
            region=settings.aws_region,
            model_id=settings.bedrock_model_id,
        )
    raise ValueError(f"Unknown AI_BACKEND: {backend}")
