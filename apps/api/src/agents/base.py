"""
BaseAgent — Clase base para todos los agentes del Copiloto.

Patrón de diseño:
  - Los agentes son stateless. Reciben un AgentContext con todo lo que necesitan.
  - Los agentes llaman al SDK de Anthropic directamente (sin langchain ni wrappers).
  - Los agentes NO acceden a la DB directamente; usan los servicios del contexto.
  - Los agentes devuelven AgentResponse — NUNCA ejecutan actos administrativos finales.
  - El "humano en el bucle" se garantiza: toda salida es un DRAFT que requiere aprobación.
"""
import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import anthropic
import structlog

from src.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


# ---------------------------------------------------------------------------
# Tipos de herramientas (tool_use) disponibles para los agentes
# ---------------------------------------------------------------------------
ToolDefinition = dict[str, Any]


# ---------------------------------------------------------------------------
# Contexto que recibe cada agente al ejecutarse
# ---------------------------------------------------------------------------
@dataclass
class AgentContext:
    """
    Contexto inmutable que se pasa a cada agente.
    Contiene toda la información y acceso a servicios que el agente puede necesitar.
    NO contiene la sesión de base de datos directamente — los servicios la gestionan.
    """
    municipio_id: UUID
    municipio_nombre: str
    municipio_config: dict[str, Any]  # configuración específica del ayuntamiento

    # Historial de conversación (formato mensajes Anthropic)
    conversation_history: list[dict[str, Any]] = field(default_factory=list)

    # Input principal del agente
    user_input: str = ""

    # Metadatos del request
    session_token: str = ""          # identificador anónimo del ciudadano
    canal: str = "web"               # "web" | "whatsapp" | "email" | "telefono"
    request_id: str = ""

    # Servicios disponibles (inyectados desde la capa de servicio)
    # Se tipan como Any para evitar imports circulares; se validan en runtime
    db_session: Any = None
    embedding_service: Any = None
    notification_service: Any = None
    audit_service: Any = None


# ---------------------------------------------------------------------------
# Respuesta estándar de cualquier agente
# ---------------------------------------------------------------------------
@dataclass
class AgentResponse:
    """
    Respuesta devuelta por cualquier agente.
    SIEMPRE es un DRAFT — requiere validación humana para actos administrativos.
    """
    content: str                              # texto principal de la respuesta
    agent_name: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    confidence: float = 1.0                   # 0.0 - 1.0
    citations: list[dict[str, Any]] = field(default_factory=list)      # fuentes citadas
    human_review_flags: list[str] = field(default_factory=list)        # aspectos a revisar
    escalate_to_human: bool = False           # si el agente recomienda derivar a persona
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0

    @property
    def cost_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# ---------------------------------------------------------------------------
# BaseAgent
# ---------------------------------------------------------------------------
class BaseAgent(ABC):
    """
    Clase base para todos los agentes del Copiloto.

    Subclases deben implementar:
      - `name`: nombre del agente
      - `system_prompt(context)`: prompt de sistema personalizado por municipio
      - `tools`: lista de herramientas disponibles (tool_use de Anthropic)
      - `run(context)`: lógica principal del agente
    """

    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre del agente (para logs y audit trail)."""
        ...

    @abstractmethod
    def system_prompt(self, context: AgentContext) -> str:
        """
        Genera el system prompt personalizado para el municipio.
        Se carga desde agents/prompts/{name}.jinja2 con variables del contexto.
        """
        ...

    @property
    def tools(self) -> list[ToolDefinition]:
        """Lista de herramientas disponibles. Por defecto, ninguna."""
        return []

    @property
    def temperature(self) -> float:
        """
        Temperatura de generación.
        - 0.1 para resoluciones (máxima consistencia legal)
        - 0.7 para chat ciudadano (conversación natural)
        """
        return 0.7

    @property
    def timeout(self) -> int:
        """Timeout en segundos para llamadas a Claude."""
        return settings.claude_timeout_chat

    @abstractmethod
    async def run(self, context: AgentContext) -> AgentResponse:
        """Ejecuta el agente y devuelve una respuesta en modo DRAFT."""
        ...

    # -------------------------------------------------------------------------
    # Métodos protegidos de utilidad para subclases
    # -------------------------------------------------------------------------

    async def _call_claude(
        self,
        context: AgentContext,
        messages: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> anthropic.types.Message:
        """
        Llama al API de Claude con manejo de errores y logging de tokens.
        """
        start = time.monotonic()

        kwargs: dict[str, Any] = {
            "model": settings.claude_model,
            "max_tokens": max_tokens,
            "temperature": self.temperature,
            "system": self.system_prompt(context),
            "messages": messages,
        }

        if self.tools:
            kwargs["tools"] = self.tools

        try:
            response = await self._client.messages.create(**kwargs)
        except anthropic.APITimeoutError:
            logger.error(
                "Timeout en llamada a Claude",
                agent=self.name,
                municipio_id=str(context.municipio_id),
                timeout=self.timeout,
            )
            raise
        except anthropic.APIError as e:
            logger.error(
                "Error en Claude API",
                agent=self.name,
                municipio_id=str(context.municipio_id),
                error_type=type(e).__name__,
            )
            raise

        duration_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "Claude API call completada",
            agent=self.name,
            municipio_id=str(context.municipio_id),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            duration_ms=duration_ms,
            # NOTA: no loguear el contenido del mensaje — puede contener PII
        )

        return response

    def _extract_text(self, response: anthropic.types.Message) -> str:
        """Extrae el texto del primer bloque de contenido de tipo 'text'."""
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""

    def _build_response(
        self,
        content: str,
        response: anthropic.types.Message,
        duration_ms: int = 0,
        **kwargs: Any,
    ) -> AgentResponse:
        """Construye un AgentResponse estándar a partir de una respuesta de Claude."""
        return AgentResponse(
            content=content,
            agent_name=self.name,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            duration_ms=duration_ms,
            **kwargs,
        )

    @staticmethod
    def _hash_session(session_token: str) -> str:
        """
        Genera un hash del session_token para el audit_log.
        NUNCA usar el session_token directamente en logs.
        """
        return hashlib.sha256(session_token.encode()).hexdigest()[:16]
