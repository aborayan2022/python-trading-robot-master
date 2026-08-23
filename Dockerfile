# ── Stage 1: Builder ────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --prefix=/install ".[alpaca,schwab,dev]"

# ── Stage 2: Runtime (production) ──────────────────────────────────
FROM python:3.12-slim AS runtime

RUN groupadd -r trader && useradd -r -g trader -d /app -s /sbin/nologin trader

WORKDIR /app

COPY --from=builder /install /usr/local
COPY pyrobot/ ./pyrobot/
COPY pyproject.toml ./

RUN mkdir -p /app/data /app/logs /tmp && \
    chown -R trader:trader /app /tmp

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "from pyrobot.runtime import TradingLoop; print('ok')" || exit 1

USER trader

# Paper-mode replay trading loop (see pyrobot/runtime/loop.py for env vars).
# This actually trades: signals → risk gates → paper fills → audit ledger.
CMD ["python", "-m", "pyrobot.runtime.loop"]

# ── Stage 3: Test (includes tests) ────────────────────────────────
FROM runtime AS test

COPY tests/ ./tests/

USER root
RUN mkdir -p /app/.pytest_cache && chown -R trader:trader /app/.pytest_cache
USER trader

CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]
