FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends g++ && rm -rf /var/lib/apt/lists/*

COPY agent/pyproject.toml agent/uv.lock ./
RUN uv sync --frozen --no-dev

COPY agent/ ./agent/

ENV PORT=8080
ENV PYTHONPATH=/app

CMD ["/app/.venv/bin/python", "-m", "uvicorn", "agent.app:app", "--host", "0.0.0.0", "--port", "8080"]
