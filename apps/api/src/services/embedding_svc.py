"""
Servicio de embeddings y búsqueda semántica en pgvector.

Usa la API de Anthropic para generar embeddings (via Voyage AI, recomendado por Anthropic)
o OpenAI text-embedding-3-small como alternativa directa.

En desarrollo sin API key configurada, usa una búsqueda de texto completo como fallback.
"""
from __future__ import annotations

import os
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Dimensión del modelo de embeddings
# text-embedding-3-small (OpenAI) → 1536 dims
# voyage-3-lite (Voyage/Anthropic) → 512 dims
EMBEDDING_DIMS = 1536


async def generate_embedding(content: str) -> list[float] | None:
    """
    Genera el vector de embedding de un texto.
    Devuelve None si no hay API key configurada (usa fallback FTS).
    """
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=openai_key)
            resp = await client.embeddings.create(
                model="text-embedding-3-small",
                input=content,
                dimensions=EMBEDDING_DIMS,
            )
            return resp.data[0].embedding
        except Exception as e:
            logger.warning("Error generando embedding con OpenAI", error=str(e))

    # Sin API de embeddings configurada → None (usará FTS)
    return None


async def search_knowledge_base(
    session: AsyncSession,
    municipio_id: UUID,
    query: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Búsqueda híbrida en la knowledge base del municipio:
    1. Si hay embeddings: cosine similarity con pgvector
    2. Fallback: full-text search con tsvector en español

    Devuelve fragmentos de documentos ordenados por relevancia.
    """
    embedding = await generate_embedding(query)

    if embedding is not None:
        # Búsqueda vectorial (cosine similarity)
        rows = await session.execute(
            text("""
                SELECT
                    id,
                    fuente_tipo,
                    fuente_nombre,
                    fuente_anyo,
                    seccion,
                    contenido,
                    1 - (embedding <=> :embedding::vector) AS score
                FROM documentos_kb
                WHERE municipio_id = :municipio_id
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> :embedding::vector
                LIMIT :limit
            """),
            {
                "municipio_id": str(municipio_id),
                "embedding": str(embedding),
                "limit": limit,
            },
        )
    else:
        # Fallback: full-text search en español
        rows = await session.execute(
            text("""
                SELECT
                    id,
                    fuente_tipo,
                    fuente_nombre,
                    fuente_anyo,
                    seccion,
                    contenido,
                    ts_rank(
                        to_tsvector('spanish', contenido),
                        plainto_tsquery('spanish', :query)
                    ) AS score
                FROM documentos_kb
                WHERE municipio_id = :municipio_id
                  AND to_tsvector('spanish', contenido) @@ plainto_tsquery('spanish', :query)
                ORDER BY score DESC
                LIMIT :limit
            """),
            {
                "municipio_id": str(municipio_id),
                "query": query,
                "limit": limit,
            },
        )

    results = []
    for row in rows.mappings():
        results.append({
            "id": str(row["id"]),
            "fuente_tipo": row["fuente_tipo"],
            "fuente_nombre": row["fuente_nombre"],
            "fuente_anyo": row["fuente_anyo"],
            "seccion": row["seccion"],
            "contenido": row["contenido"],
            "score": float(row["score"]),
        })

    return results
