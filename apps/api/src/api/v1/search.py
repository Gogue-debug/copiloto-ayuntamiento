"""Rutas: Búsqueda semántica de documentos. (Fase 2)"""
from fastapi import APIRouter

router = APIRouter(prefix="/search")


@router.get("")
async def search_documents() -> dict:
    return {"status": "coming_soon", "fase": 2}
