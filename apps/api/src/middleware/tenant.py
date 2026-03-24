"""
Middleware de Multi-tenancy.

Resuelve el municipio_id de cada request (desde subdominio o cabecera X-Municipio-Id)
y establece la variable de sesión PostgreSQL `app.current_municipio_id` para que
las políticas RLS del DB funcionen correctamente.

Flujo:
  Request → resolver municipio_id → establecer SET app.current_municipio_id en DB
"""
import re
from uuid import UUID

import structlog
from fastapi import Request, Response
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.db.session import AsyncSessionLocal

logger = structlog.get_logger()

# Rutas que no requieren resolución de tenant
TENANT_EXEMPT_PATHS = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json"}


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Resuelve el municipio_id de cada request y lo establece en la sesión PostgreSQL.

    Estrategia de resolución (en orden de prioridad):
    1. Cabecera X-Municipio-Id (UUID directo)
    2. Subdominio del Host: {slug}.copiloto.es → buscar UUID en cache/DB
    3. Si no se puede resolver y la ruta lo requiere → 400
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in TENANT_EXEMPT_PATHS:
            return await call_next(request)

        municipio_id = await self._resolve_municipio_id(request)

        if municipio_id:
            # Almacenar en el estado del request para las dependencias FastAPI
            request.state.municipio_id = municipio_id
            # Añadir cabecera normalizada para que la dependencia get_municipio_id la encuentre
            request.headers.__dict__["_list"].append(
                (b"x-municipio-id", str(municipio_id).encode())
            )

        response = await call_next(request)
        return response

    async def _resolve_municipio_id(self, request: Request) -> UUID | None:
        """Intenta resolver el municipio_id con las estrategias disponibles."""
        # Estrategia 1: cabecera directa
        header_value = request.headers.get("x-municipio-id")
        if header_value:
            try:
                return UUID(header_value)
            except ValueError:
                logger.warning("X-Municipio-Id inválido", value=header_value)
                return None

        # Estrategia 2: subdominio
        host = request.headers.get("host", "")
        slug = self._extract_slug_from_host(host)
        if slug:
            municipio_id = await self._slug_to_uuid(slug)
            if municipio_id:
                return municipio_id

        return None

    @staticmethod
    def _extract_slug_from_host(host: str) -> str | None:
        """Extrae el slug del subdominio. Ej: 'alcazar.copiloto.es' → 'alcazar'."""
        # Eliminar puerto si está presente
        host_clean = host.split(":")[0]
        parts = host_clean.split(".")
        # En producción: {slug}.copiloto.es → 3 partes
        # En desarrollo: localhost → ignorar
        if len(parts) >= 3 and not host_clean.startswith("localhost"):
            slug = parts[0]
            if re.match(r"^[a-z0-9-]+$", slug):
                return slug
        return None

    @staticmethod
    async def _slug_to_uuid(slug: str) -> UUID | None:
        """Busca el UUID de un municipio por su slug. Usa cache simple en memoria."""
        # TODO: añadir cache Redis para evitar consultas por cada request
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text("SELECT id FROM municipios WHERE slug = :slug AND activo = true"),
                    {"slug": slug},
                )
                row = result.fetchone()
                if row:
                    return UUID(str(row[0]))
        except Exception as e:
            logger.error("Error resolviendo municipio por slug", slug=slug, error=str(e))
        return None
