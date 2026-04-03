FROM python:3.12-slim

LABEL maintainer="Nexus Platform"
LABEL version="4.0.0"
LABEL description="Nexus Platform Backend — FastAPI + Celery"

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium --with-deps 2>/dev/null || true

# Copy application
COPY . .

# Create non-root user
RUN adduser --disabled-password --gecos '' nexus && \
    chown -R nexus:nexus /app

USER nexus

# Run with gunicorn + uvicorn workers
CMD ["gunicorn", "app.main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
