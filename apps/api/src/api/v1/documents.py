"""Rutas: Verificación previa de documentos. (Fase 2)"""
from fastapi import APIRouter

router = APIRouter(prefix="/documents")


@router.get("")
async def list_documents() -> dict:
    return {"status": "coming_soon", "fase": 2}
