"""Rutas: Redacción y revisión de resoluciones. (Fase 2)"""
from fastapi import APIRouter

router = APIRouter(prefix="/resolutions")


@router.get("")
async def list_resolutions() -> dict:
    return {"status": "coming_soon", "fase": 2}
