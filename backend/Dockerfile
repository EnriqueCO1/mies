# syntax=docker/dockerfile:1.6
# ==============================================================
# Mies backend — FastAPI + Tesseract OCR + PyMuPDF + Anthropic SDK
#
# The image includes the Tesseract binary with the Spanish language
# pack because `scripts/_extract.py` falls back to OCR on scanned
# PDFs (PGOU Estepona, Nerja, Torremolinos, etc.). Without it the
# extractor silently disables OCR and those PDFs come out empty.
# ==============================================================

FROM python:3.11-slim

# ── System dependencies ────────────────────────────────────────
# tesseract-ocr       — the OCR engine
# tesseract-ocr-spa   — Spanish language model (critical for Spanish normativa)
# libgl1 / libglib    — PyMuPDF's native deps for raster image ops
# build-essential     — compiling anything that ships sdist-only
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-spa \
        libgl1 \
        libglib2.0-0 \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ────────────────────────────────────────
WORKDIR /app

# Copy requirements first so layer caching works: code changes don't
# re-install dependencies unless requirements.txt itself changed.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Application code ───────────────────────────────────────────
COPY . .

# Disable output buffering so stdout/stderr stream to Railway logs in real time.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Railway injects $PORT at runtime; fall back to 8000 for local Docker runs.
# --workers 4 gives a reasonable default for ~4 concurrent chats per instance
# without ballooning memory. Tune via the START_CMD env var if needed.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 4"]
