"""Rutas: Webhooks entrantes (WhatsApp, email). (Fase 2)"""
from fastapi import APIRouter, Request

router = APIRouter(prefix="/webhooks")


@router.get("/whatsapp")
async def whatsapp_verify(request: Request) -> str:
    """Verificación del webhook de Meta (challenge-response)."""
    params = request.query_params
    if params.get("hub.verify_token") == "changeme_webhook_verify_token":
        return params.get("hub.challenge", "")
    return "Forbidden"


@router.post("/whatsapp")
async def whatsapp_inbound() -> dict:
    return {"status": "coming_soon", "fase": 2}
