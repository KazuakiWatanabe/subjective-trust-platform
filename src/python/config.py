"""アプリケーション設定モジュール。

環境変数を pydantic Settings で一元管理する。
AI_BACKEND / DATABASE_URL / ENVIRONMENT 等の設定を提供し、
ローカル・クラウド間はコード変更なしで環境変数のみで切り替え可能。

Note:
    .env.local（git 管理対象外）から自動ロードする。
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """アプリケーション全体の設定。環境変数から読み込む。"""

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- 環境識別 ---
    environment: Literal["local", "staging", "production"] = "local"

    # --- データベース ---
    database_url: str = (
        "postgresql+asyncpg://trust_user:trust_pass@localhost:5432/trust_platform"
    )

    # --- AI バックエンド ---
    ai_backend: Literal["mock", "anthropic", "bedrock"] = "mock"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # --- AWS Bedrock（ai_backend=bedrock 時） ---
    aws_region: str = "ap-northeast-1"
    bedrock_model_id: str = "anthropic.claude-sonnet-4-20250514-v1:0"

    # --- API サーバー ---
    port: int = 8080
    log_level: str = "info"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """設定シングルトンを返す。テスト時は lru_cache をクリアして差し替え可能。"""
    return Settings()
