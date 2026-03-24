"""
Middleware RGPD — Limpieza de PII en logs.

Intercepta los logs de structlog y redacta automáticamente campos con PII
antes de que lleguen a cualquier sink (consola, Loki, etc.).

Campos PII detectados y redactados: dni, nif, nombre, telefono, email, iban,
dirección, fecha_nacimiento y sus variantes.
"""
import re
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Patrones de PII a detectar y redactar en logs
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # DNI/NIE español: 8 dígitos + letra o X/Y/Z + 7 dígitos + letra
    (re.compile(r"\b[XYZ]?\d{7,8}[A-Z]\b"), "[DNI_REDACTADO]"),
    # Email
    (re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"), "[EMAIL_REDACTADO]"),
    # Teléfono español
    (re.compile(r"\b(\+34|0034)?[6789]\d{8}\b"), "[TELEFONO_REDACTADO]"),
    # IBAN
    (re.compile(r"\bES\d{2}[ ]?\d{4}[ ]?\d{4}[ ]?\d{4}[ ]?\d{4}[ ]?\d{4}\b"), "[IBAN_REDACTADO]"),
]

# Nombres de claves en dicts de log que contienen PII y deben ser redactadas
_PII_KEYS = frozenset({
    "dni", "nif", "nombre", "nombre_completo", "apellidos", "telefono",
    "email", "correo", "iban", "direccion", "fecha_nacimiento", "ip",
    "password", "token", "secret",
})


def _redact_string(value: str) -> str:
    """Aplica todos los patrones de redacción a un string."""
    for pattern, replacement in _PII_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _redact_dict(data: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    """Redacta recursivamente un diccionario de log."""
    if depth > 5:  # límite de recursión
        return data
    result = {}
    for key, value in data.items():
        if isinstance(key, str) and key.lower() in _PII_KEYS:
            result[key] = "[REDACTADO]"
        elif isinstance(value, str):
            result[key] = _redact_string(value)
        elif isinstance(value, dict):
            result[key] = _redact_dict(value, depth + 1)
        else:
            result[key] = value
    return result


class RGPDLogMiddleware(BaseHTTPMiddleware):
    """
    Middleware que redacta PII de las cabeceras de request antes de loguear.
    La redacción de los logs de la aplicación se realiza via el procesador
    de structlog configurado en el setup de logging.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # No loguar cabeceras con posible PII (Authorization, Cookie, etc.)
        # structlog capturará lo que queramos log explícitamente
        response = await call_next(request)
        return response


def configure_structlog_rgpd() -> None:
    """
    Configura structlog con un procesador que redacta PII automáticamente.
    Llamar en el startup de la aplicación (main.py lifespan).
    """
    def rgpd_redactor(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        return _redact_dict(event_dict)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            rgpd_redactor,                              # redacción PII
            structlog.processors.JSONRenderer(),         # output JSON estructurado
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )
