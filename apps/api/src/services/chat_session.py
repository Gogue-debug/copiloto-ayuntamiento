"""
Servicio de sesiones de chat.

Gestiona el historial de conversaciones en Redis (TTL 24h)
y persiste los mensajes en PostgreSQL de forma anonimizada.

La sesión se identifica por session_token — NUNCA por nombre o DNI.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# TTL de la sesión en Redis: 24 horas (ventana conversacional de WhatsApp)
SESSION_TTL_SECONDS = 86400
MAX_HISTORY_MESSAGES = 20  # Limitar contexto enviado a Claude


class ChatSessionService:
    """
    Gestiona sesiones de chat con estado en Redis y persistencia en PostgreSQL.
    """

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    # -------------------------------------------------------------------------
    # Gestión del historial en Redis
    # -------------------------------------------------------------------------

    def _session_key(self, municipio_id: UUID, session_token: str) -> str:
        return f"chat:{municipio_id}:{session_token}"

    async def get_history(
        self, municipio_id: UUID, session_token: str
    ) -> list[dict[str, Any]]:
        """Carga el historial de la sesión desde Redis."""
        key = self._session_key(municipio_id, session_token)
        try:
            raw = await self._redis.get(key)
            if raw:
                history = json.loads(raw)
                # Devolver solo los últimos N mensajes para no saturar el contexto
                return history[-MAX_HISTORY_MESSAGES:]
            return []
        except Exception as e:
            logger.warning("Error leyendo historial de Redis", error=str(e))
            return []

    async def append_message(
        self,
        municipio_id: UUID,
        session_token: str,
        role: str,
        content: str,
    ) -> None:
        """Añade un mensaje al historial de Redis y renueva el TTL."""
        key = self._session_key(municipio_id, session_token)
        try:
            raw = await self._redis.get(key)
            history: list[dict[str, Any]] = json.loads(raw) if raw else []
            history.append({"role": role, "content": content})
            await self._redis.setex(key, SESSION_TTL_SECONDS, json.dumps(history))
        except Exception as e:
            logger.warning("Error escribiendo historial en Redis", error=str(e))

    # -------------------------------------------------------------------------
    # Persistencia anonimizada en PostgreSQL
    # -------------------------------------------------------------------------

    async def ensure_conversation(
        self,
        db: AsyncSession,
        municipio_id: UUID,
        session_token: str,
        canal: str,
    ) -> UUID:
        """
        Obtiene o crea una conversación en PostgreSQL.
        Devuelve el conversation_id.
        """
        result = await db.execute(
            text("""
                SELECT id FROM conversaciones
                WHERE municipio_id = :municipio_id
                  AND session_token = :session_token
                ORDER BY iniciada_at DESC
                LIMIT 1
            """),
            {"municipio_id": str(municipio_id), "session_token": session_token},
        )
        row = result.fetchone()
        if row:
            conv_id = UUID(str(row[0]))
            # Actualizar timestamp de última actividad
            await db.execute(
                text("UPDATE conversaciones SET ultima_at = now() WHERE id = :id"),
                {"id": str(conv_id)},
            )
            return conv_id

        # Crear nueva conversación
        conv_id = uuid.uuid4()
        await db.execute(
            text("""
                INSERT INTO conversaciones (id, municipio_id, session_token, canal)
                VALUES (:id, :municipio_id, :session_token, :canal)
            """),
            {
                "id": str(conv_id),
                "municipio_id": str(municipio_id),
                "session_token": session_token,
                "canal": canal,
            },
        )
        return conv_id

    async def persist_messages(
        self,
        db: AsyncSession,
        municipio_id: UUID,
        conversation_id: UUID,
        user_message: str,
        assistant_message: str,
        tokens_input: int = 0,
        tokens_output: int = 0,
    ) -> None:
        """
        Persiste el par (user, assistant) en PostgreSQL.
        RGPD: no se almacena ninguna PII en este punto.
        """
        try:
            now = datetime.utcnow()
            for role, content, t_in, t_out in [
                ("user", user_message, 0, 0),
                ("assistant", assistant_message, tokens_input, tokens_output),
            ]:
                await db.execute(
                    text("""
                        INSERT INTO mensajes
                            (municipio_id, conversacion_id, rol, contenido, tokens_input, tokens_output)
                        VALUES
                            (:municipio_id, :conversacion_id, :rol, :contenido, :tokens_input, :tokens_output)
                    """),
                    {
                        "municipio_id": str(municipio_id),
                        "conversacion_id": str(conversation_id),
                        "rol": role,
                        "contenido": content,
                        "tokens_input": t_in,
                        "tokens_output": t_out,
                    },
                )
        except Exception as e:
            logger.error("Error persistiendo mensajes", error=str(e))
            # No propagar — la persistencia es secundaria al funcionamiento del chat
