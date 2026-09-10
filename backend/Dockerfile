# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Install system utilities if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade "pip>=24.0" && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
EXPOSE 8002

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8002"]
