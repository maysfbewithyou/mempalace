# MemPalace IEP fork — HTTP wrapper container
# version: 0.1
# phase: 2b
# locked architecture: MemPalace_Phase_2_Architecture_v0.2.md (A2, A4, A8)
#
# Build:
#   docker build -t mempalace-iep:0.1 .
#
# Run locally (smoke test):
#   docker run --rm -it \
#     -e MEMPALACE_BEARER_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
#     -p 8000:8000 \
#     -v mempalace_data:/data \
#     mempalace-iep:0.1
#
# In Coolify the same container is driven by docker-compose.coolify.yml.

ARG PYTHON_VERSION=3.12-slim


# ── Stage 1: builder ──────────────────────────────────────────────────────────
# Installs the package into a self-contained venv. Build-time deps (gcc, dev
# headers) live ONLY here; the runtime stage doesn't carry them.
FROM python:${PYTHON_VERSION} AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only what setup needs; this maximizes Docker layer cache reuse when
# code changes but pyproject hasn't.
COPY pyproject.toml README.md /build/
COPY mempalace/ /build/mempalace/

RUN python -m venv /venv \
    && /venv/bin/pip install --upgrade pip \
    && /venv/bin/pip install ".[http]"


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
# Minimal: python + the venv + curl (for HEALTHCHECK). Non-root user. HOME=/data
# so MEMPAL_PALACE_PATH=/data/.mempalace/palace satisfies Hardening Fix #14
# (palace path must be under $HOME).
FROM python:${PYTHON_VERSION} AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Volume ownership note:
# The original Dockerfile created a non-root user (mempalace:1000) and chown'd
# /data in the image. That works for `docker run --rm` testing, but on Coolify
# (and any setup mounting a fresh named volume to /data), Docker overrides the
# image-set ownership with the volume's existing ownership (root 0:0), and the
# non-root user can no longer write to /data — container crashes silently
# before logs flush. Fix: run as root in v1. Defense-in-depth via an entrypoint
# script that chowns /data and drops privileges is a nice-to-have for v2.
RUN mkdir -p /data/.mempalace /data/.cache

# Copy the venv built in stage 1.
COPY --from=builder /venv /venv

ENV PATH=/venv/bin:$PATH \
    HOME=/data \
    MEMPAL_PALACE_PATH=/data/.mempalace/palace \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_LEVEL=INFO \
    XDG_CACHE_HOME=/data/.cache

WORKDIR /data
EXPOSE 8000

# Coolify and external monitors hit /health. /health is unauthenticated
# (architecture A6) and returns "ok" / 503 based on subprocess liveness.
# /health is a lightweight liveness check (returns ok if wrapper process is alive).
# start_period=120s gives ChromaDB's first-boot ONNX model download room to finish
# without Docker killing the container in a tight restart loop.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Single-worker uvicorn — A4. Multiple workers would each spawn a separate
# stdio MCP subprocess writing to the same palace, which corrupts state.
CMD ["uvicorn", "mempalace.http_server:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1"]
