"""
Inyección de dependencias FastAPI.
Provee acceso a DB, configuración, autenticación y servicios compartidos.
"""
from typing import Annotated, AsyncGenerator
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings, get_settings
from src.db.session import AsyncSessionLocal


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
SettingsDep = Annotated[Settings, Depends(get_settings)]


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provee una sesión de base de datos por request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


DbSession = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Multi-tenancy: resolver municipio_id desde la cabecera o subdominio
# El middleware tenant.py ya ha establecido el contexto en la sesión DB.
# Esta dependencia extrae el municipio_id validado del contexto del request.
# ---------------------------------------------------------------------------
async def get_municipio_id(
    x_municipio_id: Annotated[str | None, Header()] = None,
) -> UUID:
    """
    Extrae el municipio_id del request.
    El middleware tenant.py lo resuelve desde el subdominio o cabecera
    y lo establece como variable de sesión en PostgreSQL.
    Esta dependencia sólo valida que esté presente.
    """
    if not x_municipio_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cabecera X-Municipio-Id requerida",
        )
    try:
        return UUID(x_municipio_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Municipio-Id debe ser un UUID válido",
        )


MunicipioDep = Annotated[UUID, Depends(get_municipio_id)]
