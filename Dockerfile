FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# HF Spaces requires port 7860; fallback to 8000 for local use
ENV PORT=7860

WORKDIR /app

# HF Spaces runs as non-root — ensure /app is writable
RUN chmod -R 777 /app

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Install dependencies first (layer-cached unless pyproject.toml changes)
COPY pyproject.toml ./
RUN uv pip install --system ".[dev]"

# Copy application code
COPY backend ./backend

# Copy prebuilt datasets (chunks, embeddings, Qdrant storage, semantic cache)
# These are the offline-pipeline artifacts — no rebuild needed at runtime
COPY datasets ./datasets

EXPOSE 7860

# Use shell form so $PORT is expanded at runtime
CMD uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT
