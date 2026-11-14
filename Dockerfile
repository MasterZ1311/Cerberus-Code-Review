FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install curl for healthchecks and security updates
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root user and group
RUN groupadd -g 1000 cerberus && \
    useradd -u 1000 -g cerberus -m -s /bin/bash cerberus

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Install cerberus package in editable mode and assign permissions
RUN pip install --no-cache-dir -e . && \
    chown -R cerberus:cerberus /app

USER cerberus

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["python", "-m", "cerberus.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
