# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

# Multi-stage build using openenv-base
# Stage 1 (builder): installs all dependencies into an isolated virtualenv
# Stage 2 (runtime): copies only the venv and source — no build tools in final image

ARG BASE_IMAGE=ghcr.io/meta-pytorch/openenv-base:latest
FROM ${BASE_IMAGE} AS builder

WORKDIR /app

# git is required for any VCS-sourced dependencies in pyproject.toml
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Build arguments (set by openenv build tooling; safe to ignore for manual builds)
ARG BUILD_MODE=standalone
ARG ENV_NAME=incident_triage

# Copy the full environment source into the build context
COPY . /app/env
WORKDIR /app/env

# Ensure uv is available (base image may already ship it)
RUN if ! command -v uv >/dev/null 2>&1; then \
        curl -LsSf https://astral.sh/uv/install.sh | sh && \
        mv /root/.local/bin/uv /usr/local/bin/uv && \
        mv /root/.local/bin/uvx /usr/local/bin/uvx; \
    fi

# Install dependencies declared in pyproject.toml.
# If a lockfile is present we use it for reproducible builds; otherwise
# uv resolves on the fly. Two passes: deps-only first (better layer caching),
# then the project itself.
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then \
        uv sync --frozen --no-install-project --no-editable; \
    else \
        uv sync --no-install-project --no-editable; \
    fi

RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then \
        uv sync --frozen --no-editable; \
    else \
        uv sync --no-editable; \
    fi

# ── Runtime stage ──────────────────────────────────────────────────────────
FROM ${BASE_IMAGE}

WORKDIR /app

# Bring across only the virtualenv and application source
COPY --from=builder /app/env/.venv /app/.venv
COPY --from=builder /app/env       /app/env

# Activate the virtualenv for all subsequent commands and the final CMD
ENV PATH="/app/.venv/bin:$PATH"

# Allow Python to locate the incident_triage package and server sub-package
ENV PYTHONPATH="/app/env:$PYTHONPATH"

# Liveness probe — curl must be available in the base image
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Start the FastAPI server.
# cd into /app/env so that relative imports (server.app) resolve correctly.
CMD ["sh", "-c", "cd /app/env && uvicorn server.app:app --host 0.0.0.0 --port 8000"]
