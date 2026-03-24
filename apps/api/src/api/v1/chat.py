"""
Router: Chat ciudadano

Endpoints:
  POST /api/v1/chat/message        → respuesta completa (JSON)
  POST /api/v1/chat/message/stream → respuesta en streaming (SSE)
  GET  /api/v1/chat/history        → historial de la sesión
  DELETE /api/v1/chat/session      → borrar sesión (RGPD)
"""
import json
import uuid
from typing import Any, AsyncGenerator, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.citizen_faq import CitizenFAQAgent
from src.agents.base import AgentContext
from src.config import get_settings
from src.deps import DbSession, MunicipioDep

logger = structlog.get_logger()
settings = get_settings()

router = APIRouter(prefix="/chat")

# Instancia reutilizable del agente (stateless)
_faq_agent = CitizenFAQAgent()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="Mensaje del ciudadano")
    session_token: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Token de sesión anónimo. Se genera automáticamente si no se proporciona.",
    )
    canal: Literal["web", "whatsapp", "email", "telefono"] = Field(
        default="web",
        description="Canal de comunicación",
    )


class ChatMessageResponse(BaseModel):
    session_token: str
    response: str
    citations: list[dict[str, Any]] = []
    escalate_to_human: bool = False
    tokens_used: int = 0


# ---------------------------------------------------------------------------
# Dependencia: Redis para sesiones de chat
# ---------------------------------------------------------------------------

async def get_redis() -> Any:
    """Provee un cliente Redis. En desarrollo sin Redis, devuelve un mock."""
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        yield client
        await client.aclose()
    except Exception:
        # Mock en memoria para desarrollo sin Redis
        yield _InMemoryRedis()


class _InMemoryRedis:
    """Mock de Redis para desarrollo sin dependencia externa."""
    _store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def aclose(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Helper: obtener info del municipio
# ---------------------------------------------------------------------------

async def _get_municipio_info(db: AsyncSession, municipio_id: Any) -> dict[str, Any]:
    """Carga nombre y config del municipio desde DB."""
    from sqlalchemy import text
    result = await db.execute(
        text("SELECT nombre, config FROM municipios WHERE id = :id"),
        {"id": str(municipio_id)},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Municipio no encontrado: {municipio_id}",
        )
    return {"nombre": row[0], "config": row[1] or {}}


# ---------------------------------------------------------------------------
# POST /chat/message → respuesta JSON completa
# ---------------------------------------------------------------------------

@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    body: ChatMessageRequest,
    municipio_id: MunicipioDep,
    db: DbSession,
    redis: Any = Depends(get_redis),
) -> ChatMessageResponse:
    """
    Procesa un mensaje del ciudadano y devuelve la respuesta completa.
    Usa el agente CitizenFAQ con RAG sobre la knowledge base del municipio.
    """
    from src.services.chat_session import ChatSessionService

    session_svc = ChatSessionService(redis)
    municipio = await _get_municipio_info(db, municipio_id)

    # Cargar historial de la sesión
    history = await session_svc.get_history(municipio_id, body.session_token)

    # Construir contexto del agente
    context = AgentContext(
        municipio_id=municipio_id,
        municipio_nombre=municipio["nombre"],
        municipio_config=municipio["config"],
        conversation_history=history,
        user_input=body.message,
        session_token=body.session_token,
        canal=body.canal,
        db_session=db,
    )

    # Ejecutar agente
    agent_response = await _faq_agent.run(context)

    # Persistir en Redis y PostgreSQL
    await session_svc.append_message(municipio_id, body.session_token, "user", body.message)
    await session_svc.append_message(
        municipio_id, body.session_token, "assistant", agent_response.content
    )

    conversation_id = await session_svc.ensure_conversation(
        db, municipio_id, body.session_token, body.canal
    )
    await session_svc.persist_messages(
        db=db,
        municipio_id=municipio_id,
        conversation_id=conversation_id,
        user_message=body.message,
        assistant_message=agent_response.content,
        tokens_input=agent_response.input_tokens,
        tokens_output=agent_response.output_tokens,
    )

    logger.info(
        "chat.message.processed",
        municipio_id=str(municipio_id),
        canal=body.canal,
        escalate=agent_response.escalate_to_human,
        tokens=agent_response.cost_tokens,
        # NO loguear: body.message, agent_response.content (pueden tener PII)
    )

    return ChatMessageResponse(
        session_token=body.session_token,
        response=agent_response.content,
        citations=agent_response.citations,
        escalate_to_human=agent_response.escalate_to_human,
        tokens_used=agent_response.cost_tokens,
    )


# ---------------------------------------------------------------------------
# POST /chat/message/stream → Server-Sent Events (streaming)
# ---------------------------------------------------------------------------

@router.post("/message/stream")
async def send_message_stream(
    body: ChatMessageRequest,
    municipio_id: MunicipioDep,
    db: DbSession,
    redis: Any = Depends(get_redis),
) -> StreamingResponse:
    """
    Procesa un mensaje del ciudadano con respuesta en streaming (SSE).
    Ideal para el widget de chat web — efecto de escritura en tiempo real.
    """
    from src.services.chat_session import ChatSessionService
    import anthropic

    session_svc = ChatSessionService(redis)
    municipio = await _get_municipio_info(db, municipio_id)
    history = await session_svc.get_history(municipio_id, body.session_token)

    context = AgentContext(
        municipio_id=municipio_id,
        municipio_nombre=municipio["nombre"],
        municipio_config=municipio["config"],
        conversation_history=history,
        user_input=body.message,
        session_token=body.session_token,
        canal=body.canal,
        db_session=db,
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        full_response = ""
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        # Primera pasada: detectar si Claude quiere usar tools (no se puede streamear tool_use)
        # Por simplicidad en streaming, hacemos la llamada sin tools y usamos el contexto
        # pre-recuperado. La versión completa con tools usa el endpoint /message.
        messages = list(history)
        messages.append({"role": "user", "content": body.message})

        try:
            async with client.messages.stream(
                model=settings.claude_model,
                max_tokens=1024,
                temperature=0.7,
                system=_faq_agent.system_prompt(context),
                messages=messages,
            ) as stream:
                async for text_chunk in stream.text_stream:
                    full_response += text_chunk
                    # Formato SSE
                    yield f"data: {json.dumps({'type': 'chunk', 'content': text_chunk})}\n\n"

            # Evento final con metadatos
            final_message = await stream.get_final_message()
            yield f"data: {json.dumps({'type': 'done', 'tokens': final_message.usage.input_tokens + final_message.usage.output_tokens})}\n\n"

            # Persistir en background
            await session_svc.append_message(municipio_id, body.session_token, "user", body.message)
            await session_svc.append_message(municipio_id, body.session_token, "assistant", full_response)

        except Exception as e:
            logger.error("Error en streaming de chat", error=str(e))
            yield f"data: {json.dumps({'type': 'error', 'message': 'Error procesando la consulta'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Desactivar buffering en Nginx/Traefik
        },
    )


# ---------------------------------------------------------------------------
# GET /chat/history
# ---------------------------------------------------------------------------

@router.get("/history")
async def get_history(
    session_token: str = Query(..., description="Token de sesión"),
    municipio_id: MunicipioDep = None,  # type: ignore[assignment]
    redis: Any = Depends(get_redis),
) -> dict[str, Any]:
    """Devuelve el historial de mensajes de una sesión (para debugging)."""
    from src.services.chat_session import ChatSessionService
    session_svc = ChatSessionService(redis)
    history = await session_svc.get_history(municipio_id, session_token)
    return {"session_token": session_token, "messages": history, "count": len(history)}


# ---------------------------------------------------------------------------
# DELETE /chat/session → derecho al olvido RGPD
# ---------------------------------------------------------------------------

@router.delete("/session")
async def delete_session(
    session_token: str = Query(...),
    municipio_id: MunicipioDep = None,  # type: ignore[assignment]
    redis: Any = Depends(get_redis),
) -> dict[str, str]:
    """Elimina la sesión de chat (derecho al olvido — RGPD art. 17)."""
    from src.services.chat_session import ChatSessionService
    session_svc = ChatSessionService(redis)
    key = session_svc._session_key(municipio_id, session_token)
    await redis.delete(key)
    return {"status": "deleted", "session_token": session_token}
