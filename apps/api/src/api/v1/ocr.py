"""Rutas: OCR de facturas y justificantes. (Fase 1 — semana 7-8)"""
from fastapi import APIRouter

router = APIRouter(prefix="/ocr")


@router.get("/batches")
async def list_batches() -> dict:
    return {"status": "coming_soon", "fase": 1, "semana": "7-8"}
