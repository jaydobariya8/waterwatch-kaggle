# WaterWatch — reproducible Cloud Run container.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt requirements-cloud.txt ./
RUN pip install --upgrade pip && pip install -r requirements-cloud.txt

# Copy the application.
COPY waterwatch ./waterwatch
COPY mcp_server ./mcp_server
COPY frontend ./frontend
COPY eval ./eval
COPY pyproject.toml ./

EXPOSE 8080

# Cloud Run provides $PORT. Bind to it.
CMD ["sh", "-c", "uvicorn waterwatch.main:app --host 0.0.0.0 --port ${PORT}"]
