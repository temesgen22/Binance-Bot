FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

# System deps (keep build-essential if you have wheels that need compiling)
# curl is needed for health checks in docker-compose
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better caching)
COPY requirements.txt ${APP_HOME}/requirements.txt
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . ${APP_HOME}

# Create non-root user and switch
RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app ${APP_HOME}
USER app

EXPOSE 8000

# Health check configuration (matches docker-compose.prod.yml)
# interval: 10s, timeout: 10s (increased for Redis checks), start-period: 120s, retries: 12
HEALTHCHECK --interval=10s --timeout=10s --start-period=120s --retries=12 \
  CMD curl -fsS --max-time 8 http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]