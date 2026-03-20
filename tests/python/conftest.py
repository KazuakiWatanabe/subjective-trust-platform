"""テスト共通設定。

pytest のフィクスチャ・設定を定義する。

Note:
    DB を使うテストは integration マーカーを付けること。
"""

import os

# テスト実行時は .env.local を読み込まないようにする
os.environ.setdefault("AI_BACKEND", "mock")
os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://trust_user:trust_pass@db:5432/trust_platform",
)
