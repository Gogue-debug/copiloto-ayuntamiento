#!/usr/bin/env python3
"""
Script de ingestión de knowledge base.

Lee documentos (PDF, Word, YAML) de un directorio y los convierte en
embeddings vectoriales almacenados en PostgreSQL/pgvector para búsqueda semántica.

Uso:
    uv run python scripts/seed_knowledge_base.py \\
        --municipio-slug alcazar-san-juan \\
        --path knowledge-base/template/

Tipos de documentos soportados:
  - ordenanzas/    → PDFs de ordenanzas municipales
  - plantillas/    → Plantillas Word (.docx) de resoluciones
  - faqs/          → YAMLs con preguntas y respuestas frecuentes
  - procedimientos/→ YAMLs con definición de trámites y documentación requerida
"""
import argparse
import asyncio
import sys
import uuid
from pathlib import Path
from typing import Iterator

# Añadir el directorio apps/api al path
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "api"))

try:
    from src.config import get_settings
    settings = get_settings()
except Exception as e:
    print(f"Error cargando configuración: {e}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Chunking de texto
# ---------------------------------------------------------------------------
def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
    """
    Divide texto en chunks con overlap.
    Respeta límites de párrafo cuando es posible.
    """
    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])

        # Intentar terminar en límite de oración
        if end < len(words):
            last_period = max(chunk.rfind(". "), chunk.rfind(".\n"))
            if last_period > len(chunk) * 0.5:  # solo si el punto está en la segunda mitad
                chunk = chunk[: last_period + 1]

        chunks.append(chunk.strip())
        start = end - overlap

    return [c for c in chunks if len(c.split()) > 10]  # filtrar chunks muy cortos


# ---------------------------------------------------------------------------
# Lectores de documentos
# ---------------------------------------------------------------------------
def read_pdf(path: Path) -> str:
    """Extrae texto de un PDF."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        print("  ⚠ pypdf no instalado. Instala con: uv add pypdf")
        return ""


def read_docx(path: Path) -> str:
    """Extrae texto de un archivo Word."""
    try:
        from docx import Document
        doc = Document(str(path))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        print("  ⚠ python-docx no instalado. Instala con: uv add python-docx")
        return ""


def read_yaml_faq(path: Path) -> list[dict[str, str]]:
    """Lee un YAML de FAQs. Formato esperado: lista de {pregunta, respuesta}."""
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"  ⚠ Error leyendo YAML {path.name}: {e}")
        return []


# ---------------------------------------------------------------------------
# Generación de embeddings
# ---------------------------------------------------------------------------
async def generate_embedding(text: str) -> list[float]:
    """
    Genera el embedding de un texto usando la API de Anthropic.
    En producción considerar text-embedding-3-small de OpenAI para batch eficiente.
    """
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Anthropic no tiene endpoint de embeddings propio todavía —
    # usamos OpenAI text-embedding-3-small como alternativa recomendada.
    # Si solo quieres usar Anthropic, implementa con voyage-ai (recomendado por Anthropic).
    raise NotImplementedError(
        "Configura el proveedor de embeddings en src/services/embedding_svc.py. "
        "Opciones: OpenAI text-embedding-3-small, Voyage AI (recomendado por Anthropic)."
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingestar knowledge base en pgvector")
    parser.add_argument("--municipio-slug", required=True, help="Slug del municipio")
    parser.add_argument("--path", required=True, help="Ruta al directorio de documentos")
    parser.add_argument("--chunk-size", type=int, default=512, help="Tamaño del chunk en palabras")
    parser.add_argument("--overlap", type=int, default=50, help="Overlap entre chunks")
    parser.add_argument("--dry-run", action="store_true", help="Mostrar chunks sin guardar en DB")
    args = parser.parse_args()

    base_path = Path(args.path)
    if not base_path.exists():
        print(f"Error: El directorio {base_path} no existe")
        sys.exit(1)

    # Obtener municipio_id
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

    engine = create_async_engine(settings.database_url, echo=False)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as session:
        result = await session.execute(
            text("SELECT id FROM municipios WHERE slug = :slug AND activo = true"),
            {"slug": args.municipio_slug},
        )
        row = result.fetchone()
        if not row:
            print(f"Error: No se encontró municipio con slug {args.municipio_slug!r}")
            sys.exit(1)
        municipio_id = uuid.UUID(str(row[0]))

    print(f"\nIngestando knowledge base para municipio: {args.municipio_slug}")
    print(f"Municipio ID: {municipio_id}")
    print(f"Directorio: {base_path}")
    print("=" * 60)

    total_chunks = 0

    # Procesar cada tipo de documento
    for subdir_name, fuente_tipo in [
        ("ordenanzas", "ordenanza"),
        ("plantillas", "plantilla"),
        ("faqs", "faq"),
        ("procedimientos", "procedimiento"),
        ("actas", "acta"),
        ("bandos", "bando"),
    ]:
        subdir = base_path / subdir_name
        if not subdir.exists():
            continue

        print(f"\nProcesando {subdir_name}/...")

        for file_path in sorted(subdir.iterdir()):
            if file_path.is_dir():
                continue

            # Leer contenido según extensión
            content = ""
            chunks_data: list[dict] = []

            if file_path.suffix.lower() == ".pdf":
                content = read_pdf(file_path)
                if content:
                    chunks = chunk_text(content, args.chunk_size, args.overlap)
                    chunks_data = [
                        {
                            "fuente_tipo": fuente_tipo,
                            "fuente_nombre": file_path.stem,
                            "seccion": None,
                            "chunk_index": i,
                            "contenido": chunk,
                        }
                        for i, chunk in enumerate(chunks)
                    ]

            elif file_path.suffix.lower() in (".docx", ".doc"):
                content = read_docx(file_path)
                if content:
                    chunks = chunk_text(content, args.chunk_size, args.overlap)
                    chunks_data = [
                        {
                            "fuente_tipo": fuente_tipo,
                            "fuente_nombre": file_path.stem,
                            "seccion": None,
                            "chunk_index": i,
                            "contenido": chunk,
                        }
                        for i, chunk in enumerate(chunks)
                    ]

            elif file_path.suffix.lower() in (".yaml", ".yml"):
                faqs = read_yaml_faq(file_path)
                for i, faq in enumerate(faqs):
                    pregunta = faq.get("pregunta", "")
                    respuesta = faq.get("respuesta", "")
                    if pregunta and respuesta:
                        chunks_data.append({
                            "fuente_tipo": fuente_tipo,
                            "fuente_nombre": file_path.stem,
                            "seccion": pregunta[:100],
                            "chunk_index": i,
                            "contenido": f"Pregunta: {pregunta}\n\nRespuesta: {respuesta}",
                        })
            else:
                continue  # Extensión no soportada

            if not chunks_data:
                print(f"  ⚠ {file_path.name}: sin contenido extraíble")
                continue

            print(f"  ✓ {file_path.name}: {len(chunks_data)} chunks")
            total_chunks += len(chunks_data)

            if args.dry_run:
                for chunk in chunks_data[:2]:  # mostrar primeros 2 en dry-run
                    print(f"    [{chunk['chunk_index']}] {chunk['contenido'][:80]}...")
                continue

            # TODO: generar embeddings e insertar en DB
            # async with SessionLocal() as session:
            #     for chunk_data in chunks_data:
            #         embedding = await generate_embedding(chunk_data["contenido"])
            #         await session.execute(
            #             text("INSERT INTO documentos_kb ..."),
            #             {..., "embedding": embedding, "municipio_id": municipio_id}
            #         )
            #     await session.commit()

            print(f"    → Embeddings pendientes de configurar (ver src/services/embedding_svc.py)")

    await engine.dispose()

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}Total chunks procesados: {total_chunks}")
    print("\nPróximos pasos:")
    print("  1. Configurar proveedor de embeddings en src/services/embedding_svc.py")
    print("  2. Ejecutar sin --dry-run para guardar en la base de datos")


if __name__ == "__main__":
    asyncio.run(main())
