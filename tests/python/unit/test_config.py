"""config.py のユニットテスト。

対象: src/python/config.py
テスト観点: 環境変数による設定読み込み・AI_BACKEND 切り替え・デフォルト値

Args:
    なし
Returns:
    なし
Note:
    実際の AI API・DB への接続は行わない。
"""

import os
from unittest.mock import patch

import pytest

from src.python.config import Settings


class TestSettings:
    """Settings クラスのテスト。"""

    # AC-01: mypy strict / ruff / pytest が pyproject.toml で設定されている
    # → pyproject.toml の存在はプロジェクト構造テストで検証

    # AC-02: 環境変数は config.py の pydantic Settings で一元管理される
    def test_デフォルト設定が正しく読み込まれる(self) -> None:
        """環境変数未設定時のデフォルト値を検証する。"""
        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.environment == "local"
        assert settings.ai_backend == "mock"
        assert settings.port == 8080

    def test_環境変数から設定を読み込める(self) -> None:
        """環境変数で設定を上書きできることを検証する。"""
        env = {
            "ENVIRONMENT": "production",
            "AI_BACKEND": "anthropic",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@host:5432/db",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = Settings(
                _env_file=None,  # type: ignore[call-arg]
            )
            assert settings.environment == "production"
            assert settings.ai_backend == "anthropic"
            assert settings.anthropic_api_key == "sk-ant-test"

    # AC-03: AI_BACKEND=mock のとき MockInterpretationClient が自動選択される
    @pytest.mark.parametrize(
        "backend",
        ["mock", "anthropic", "bedrock"],
    )
    def test_AI_BACKENDの全選択肢が有効(self, backend: str) -> None:
        """AI_BACKEND の 3 種類がすべてバリデーションを通過する。"""
        with patch.dict(os.environ, {"AI_BACKEND": backend}, clear=False):
            settings = Settings(
                _env_file=None,  # type: ignore[call-arg]
            )
            assert settings.ai_backend == backend

    def test_不正なAI_BACKENDはバリデーションエラー(self) -> None:
        """AI_BACKEND に未知の値を指定した場合にエラーになる。"""
        with patch.dict(os.environ, {"AI_BACKEND": "invalid"}, clear=False):
            with pytest.raises(Exception):
                Settings(
                    _env_file=None,  # type: ignore[call-arg]
                )

    # AC-04: .env.example に必要な変数がすべて記載されている
    def test_env_exampleに必要な変数が記載されている(self) -> None:
        """`.env.example` に必須の環境変数キーが含まれていることを検証する。"""
        env_example_path = "C:/Git/subjective-trust-platform/.env.example"
        with open(env_example_path, encoding="utf-8") as f:
            content = f.read()
        required_keys = ["AI_BACKEND", "ANTHROPIC_API_KEY", "DATABASE_URL", "ENVIRONMENT"]
        for key in required_keys:
            assert key in content, f".env.example に {key} が記載されていない"
