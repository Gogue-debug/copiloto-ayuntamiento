#!/usr/bin/env python3
"""
Script de onboarding: crea un nuevo municipio (tenant) en el sistema.

Uso:
    uv run python scripts/create_municipality.py --name "Ayuntamiento de Alcázar de San Juan" --slug alcazar-san-juan

El script:
  1. Crea el registro en la tabla municipios
  2. Crea el bucket MinIO del municipio
  3. Muestra las instrucciones para configurar Keycloak y Traefik
"""
import argparse
import asyncio
import sys
import uuid
from pathlib import Path

# Añadir el directorio apps/api al path
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "api"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

try:
    from src.config import get_settings
    settings = get_settings()
except Exception as e:
    print(f"Error cargando configuración: {e}")
    print("Asegúrate de haber copiado .env.example a .env y rellenado los valores.")
    sys.exit(1)


async def create_municipio(
    session: AsyncSession,
    nombre: str,
    slug: str,
    dominio: str | None = None,
) -> uuid.UUID:
    """Crea el municipio en PostgreSQL."""
    municipio_id = uuid.uuid4()
    await session.execute(
        text("""
            INSERT INTO municipios (id, nombre, slug, dominio, config, activo)
            VALUES (:id, :nombre, :slug, :dominio, :config::jsonb, true)
        """),
        {
            "id": str(municipio_id),
            "nombre": nombre,
            "slug": slug,
            "dominio": dominio or f"{slug}.copiloto.es",
            "config": "{}",
        },
    )
    await session.commit()
    return municipio_id


async def create_minio_bucket(municipio_id: uuid.UUID, slug: str) -> None:
    """Crea el prefijo de bucket en MinIO para el municipio."""
    try:
        from minio import Minio

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

        bucket = settings.minio_bucket
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            print(f"  ✓ Bucket MinIO creado: {bucket}")
        else:
            print(f"  ✓ Bucket MinIO ya existe: {bucket}")

        # Crear un objeto marcador para el prefijo del municipio
        import io
        marker = f"{municipio_id}/.municipio"
        client.put_object(
            bucket,
            marker,
            io.BytesIO(slug.encode()),
            len(slug),
        )
        print(f"  ✓ Prefijo MinIO creado: {municipio_id}/")

    except Exception as e:
        print(f"  ⚠ No se pudo crear el bucket MinIO: {e}")
        print("    Asegúrate de que MinIO está arriba: docker compose up -d minio")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Crear nuevo municipio en Copiloto")
    parser.add_argument("--name", required=True, help='Nombre completo, e.g. "Ayuntamiento de X"')
    parser.add_argument("--slug", required=True, help='Slug URL, e.g. "alcazar-san-juan"')
    parser.add_argument("--dominio", help="Dominio personalizado (opcional)")
    args = parser.parse_args()

    # Validar slug
    import re
    if not re.match(r"^[a-z0-9-]+$", args.slug):
        print("Error: El slug solo puede contener letras minúsculas, números y guiones.")
        sys.exit(1)

    print(f"\nCreando municipio: {args.name!r} (slug: {args.slug!r})")
    print("=" * 60)

    engine = create_async_engine(settings.database_url, echo=False)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as session:
        # Verificar que no existe ya el slug
        result = await session.execute(
            text("SELECT id FROM municipios WHERE slug = :slug"),
            {"slug": args.slug},
        )
        if result.fetchone():
            print(f"Error: Ya existe un municipio con slug {args.slug!r}")
            sys.exit(1)

        print("  Creando registro en base de datos...")
        municipio_id = await create_municipio(session, args.name, args.slug, args.dominio)
        print(f"  ✓ Municipio creado con ID: {municipio_id}")

    print("  Configurando almacenamiento MinIO...")
    await create_minio_bucket(municipio_id, args.slug)

    await engine.dispose()

    # Instrucciones manuales
    dominio = args.dominio or f"{args.slug}.copiloto.es"
    print("\n" + "=" * 60)
    print("MUNICIPIO CREADO CORRECTAMENTE")
    print("=" * 60)
    print(f"\nID del municipio: {municipio_id}")
    print(f"Slug: {args.slug}")
    print(f"Dominio: {dominio}")
    print("\nPasos siguientes:")
    print(f"  1. Ingestar knowledge base:")
    print(f"     uv run python scripts/seed_knowledge_base.py \\")
    print(f"       --municipio-slug {args.slug} \\")
    print(f"       --path knowledge-base/template/")
    print(f"\n  2. Configurar Keycloak:")
    print(f"     - Crear grupo '{args.slug}' en realm 'copiloto'")
    print(f"     - Asignar usuarios del ayuntamiento al grupo")
    print(f"\n  3. Configurar DNS:")
    print(f"     - Añadir registro A: {dominio} → IP del servidor")
    print(f"\n  4. (Opcional) Personalizar config del municipio:")
    print(f"     UPDATE municipios SET config = '{{...}}' WHERE slug = '{args.slug}';")


if __name__ == "__main__":
    asyncio.run(main())
