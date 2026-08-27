# ── Stage 1a: Runtime dependencies ───────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --prefix=/install ".[alpaca,schwab,console,ml]"

# ── Stage 1b: Test dependencies (extends runtime) ───────────────
FROM builder AS test-builder

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --prefix=/install ".[dev]"

# ── Stage 2: Runtime / Console ──────────────────────────────────
FROM python:3.12-slim AS runtime

RUN groupadd -r trader && useradd -r -g trader -d /app -s /sbin/nologin trader

WORKDIR /app

COPY --from=builder /install /usr/local
COPY pyrobot/ ./pyrobot/

RUN mkdir -p /app/data /app/logs && \
    chown -R trader:trader /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PYROBOT_CONSOLE_HOST=0.0.0.0 \
    PYROBOT_CONSOLE_PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=5)" || exit 1

USER trader

# Launch the unified Management Console + background trading loop
CMD ["python", "-m", "pyrobot.console"]

# ── Stage 3: Test (includes tests + dev tools) ─────────────────
FROM runtime AS test

COPY --from=test-builder /install /usr/local
COPY tests/ ./tests/

USER root
RUN mkdir -p /app/.pytest_cache && chown -R trader:trader /app/.pytest_cache
USER trader

CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]
