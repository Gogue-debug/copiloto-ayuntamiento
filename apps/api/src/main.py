"""
Copiloto Administrativo para Ayuntamientos — FastAPI Application
"""
import structlog
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings
from src.middleware.audit import AuditMiddleware
from src.middleware.rgpd import RGPDLogMiddleware, configure_structlog_rgpd

# Importar routers
from src.api.v1 import chat, appointments, documents, ocr, resolutions, search, webhooks

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Ciclo de vida de la aplicación: startup y shutdown."""
    configure_structlog_rgpd()
    logger.info(
        "Iniciando Copiloto Administrativo",
        env=settings.app_env,
        model=settings.claude_model,
    )
    yield
    logger.info("Apagando Copiloto Administrativo")


app = FastAPI(
    title="Copiloto Administrativo para Ayuntamientos",
    description=(
        "Plataforma de agentes de IA para modernizar la administración municipal española. "
        "Cumple Ley 39/2015 (humano en el bucle), RGPD y ENS."
    ),
    version="0.1.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middlewares (orden importa: se ejecutan de dentro hacia fuera)
# ---------------------------------------------------------------------------
app.add_middleware(RGPDLogMiddleware)          # 1. Limpia PII de logs
app.add_middleware(AuditMiddleware)             # 2. Registra acciones en audit_log

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Métricas Prometheus (opcional)
# ---------------------------------------------------------------------------
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Routers API v1
# ---------------------------------------------------------------------------
api_prefix = "/api/v1"

app.include_router(chat.router, prefix=api_prefix, tags=["Chat ciudadano"])
app.include_router(appointments.router, prefix=api_prefix, tags=["Citas"])
app.include_router(documents.router, prefix=api_prefix, tags=["Documentos"])
app.include_router(ocr.router, prefix=api_prefix, tags=["OCR Facturas"])
app.include_router(resolutions.router, prefix=api_prefix, tags=["Resoluciones"])
app.include_router(search.router, prefix=api_prefix, tags=["Búsqueda semántica"])
app.include_router(webhooks.router, prefix=api_prefix, tags=["Webhooks"])


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Sistema"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
