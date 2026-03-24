"""
Middleware de Auditoría ENS.

Registra en el audit_log todas las operaciones sobre recursos sensibles
(resoluciones, facturas, expedientes) con sus transiciones de estado.

Este middleware NO registra el contenido de los mensajes (PII potencial),
solo las acciones y sus metadatos.
"""
import hashlib
import time
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger()

# Métodos y paths que generan entradas de audit log
_AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_AUDIT_PATH_PREFIXES = (
    "/api/v1/resolutions",
    "/api/v1/ocr",
    "/api/v1/expedientes",
    "/api/v1/documents",
)


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware de auditoría: registra operaciones sensibles en el audit_log.
    No bloquea el request — el registro es asíncrono (via Celery si hay errores).
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self._should_audit(request):
            return await call_next(request)

        start = time.monotonic()
        response = await call_next(request)
        duration_ms = int((time.monotonic() - start) * 1000)

        # Registrar solo en respuestas exitosas (2xx)
        if 200 <= response.status_code < 300:
            await self._log_audit(request, response, duration_ms)

        return response

    def _should_audit(self, request: Request) -> bool:
        if request.method not in _AUDITED_METHODS:
            return False
        return any(request.url.path.startswith(prefix) for prefix in _AUDIT_PATH_PREFIXES)

    async def _log_audit(
        self, request: Request, response: Response, duration_ms: int
    ) -> None:
        """Registra la acción en el audit_log estructurado."""
        ip = request.client.host if request.client else "unknown"
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]

        municipio_id = getattr(request.state, "municipio_id", None)

        logger.info(
            "audit.request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            municipio_id=str(municipio_id) if municipio_id else None,
            ip_hash=ip_hash,
            # NO loguear: body, query params con posible PII, cabeceras de auth
        )
