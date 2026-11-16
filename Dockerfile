# =========================================================================
# Cerberus Multi-Agent Code Review Service - Multi-Stage Production Dockerfile
# Pinned by immutable sha256 digest, non-root user, and strict readiness probe
# =========================================================================

# Stage 1: Build & Dependency Wheel Compilation
FROM python:3.11-slim@sha256:d8c525f0ad0289a4ffad6d14902b79a52de0db126e855fa316d2eb1fcebc95ba AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment for deterministic isolation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements-lock.txt requirements.txt ./
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements-lock.txt

# Stage 2: Minimal Hardened Runtime
FROM python:3.11-slim@sha256:d8c525f0ad0289a4ffad6d14902b79a52de0db126e855fa316d2eb1fcebc95ba AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    ENVIRONMENT=production

# Install curl for container healthcheck probe and security updates
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dedicated unprivileged non-root user
RUN groupadd -g 1000 cerberus && \
    useradd -u 1000 -g cerberus -m -s /bin/bash cerberus

# Copy pre-built virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application source tree
COPY --chown=cerberus:cerberus . /app

# Install application package in non-editable standard distribution mode
RUN pip install --no-cache-dir --no-deps . && \
    chown -R cerberus:cerberus /app

USER cerberus

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8000/api/v1/ready || exit 1

CMD ["python", "-m", "cerberus.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
