"""Rutas: Gestión de citas previas. (Fase 2)"""
from fastapi import APIRouter

router = APIRouter(prefix="/appointments")


@router.get("")
async def list_appointments() -> dict:
    return {"status": "coming_soon", "fase": 2}
