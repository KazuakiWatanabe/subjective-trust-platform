FROM python:3.12-slim

WORKDIR /app

# 依存関係のインストール（キャッシュ活用のため先にコピー）
COPY pyproject.toml .
# src/ がないと editable install できないため、まず空構造を作成
COPY src/ ./src/
RUN pip install --no-cache-dir -e ".[dev]"

COPY tests/ ./tests/
COPY scripts/ ./scripts/
COPY alembic.ini .

# src.python.xxx 形式の import を解決するために /app をパスに含める
ENV PYTHONPATH=/app
ENV PORT=8080

CMD ["uvicorn", "src.python.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
