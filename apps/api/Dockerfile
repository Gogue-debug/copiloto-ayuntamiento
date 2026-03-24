# =============================================================================
# Copiloto API — Dockerfile multi-stage
# =============================================================================

# ---------------------------------------------------------------------------
# Base: dependencias comunes
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tesseract-ocr \
    tesseract-ocr-spa \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar uv (gestor de paquetes rápido)
RUN pip install uv==0.5.11

WORKDIR /app
COPY pyproject.toml .

# ---------------------------------------------------------------------------
# Desarrollo: instala todo (incluyendo dev dependencies)
# ---------------------------------------------------------------------------
FROM base AS development

RUN uv sync --extra dev
COPY . .
EXPOSE 8000

# ---------------------------------------------------------------------------
# Producción: sin dev dependencies, imagen mínima
# ---------------------------------------------------------------------------
FROM base AS production

RUN uv sync --no-dev
COPY . .
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
