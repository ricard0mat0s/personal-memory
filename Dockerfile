# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:latest AS uv

FROM python:3.12-slim

# Install git (required by GitUpdateRecorder) and CA certificates (required for Auth0 JWKS)
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and the default mount point for the memory Git workspace
RUN useradd --create-home --uid 1000 --shell /bin/bash appuser \
    && mkdir -p /workspace \
    && chown appuser:appuser /workspace

# Fallback Git identity and safe.directory for mounted workspaces
RUN git config --system user.name "Personal Memory Server" \
    && git config --system user.email "personal-memory@localhost" \
    && git config --system --add safe.directory /workspace

WORKDIR /app

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    MCP_HOST=0.0.0.0 \
    PATH="/app/.venv/bin:$PATH"

# Install locked runtime dependencies first for better layer caching
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --locked --no-dev --no-editable \
    && chown -R appuser:appuser /app

USER appuser

VOLUME ["/workspace"]
EXPOSE 8000

ENTRYPOINT ["personal-memory-server"]
CMD ["/workspace"]
