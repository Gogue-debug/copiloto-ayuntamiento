"""
Configuración de Celery con Redis como broker.

Colas:
  - queue.ocr          → extracción de facturas (30-60s)
  - queue.embeddings   → ingestión knowledge base (baja prioridad)
  - queue.notifications→ WhatsApp/email/SMS (máxima prioridad)
  - queue.reports      → borradores de resoluciones (5-15s)
  - queue.sync         → sincronización Gestiona/Sedipualba (1 worker)
"""
from celery import Celery
from src.config import get_settings

settings = get_settings()

celery_app = Celery(
    "copiloto",
    broker=settings.redis_celery_url,
    backend=settings.redis_url.replace("/0", "/2"),
    include=[
        "src.workers.ocr_tasks",
        "src.workers.embedding_tasks",
        "src.workers.notification_tasks",
        "src.workers.report_tasks",
    ],
)

celery_app.conf.update(
    # Serialización
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Madrid",
    enable_utc=True,

    # Reintentos con backoff exponencial
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_max_retries=4,
    task_default_retry_delay=5,  # segundos

    # Rutas de colas
    task_routes={
        "src.workers.ocr_tasks.*": {"queue": "queue.ocr"},
        "src.workers.embedding_tasks.*": {"queue": "queue.embeddings"},
        "src.workers.notification_tasks.*": {"queue": "queue.notifications"},
        "src.workers.report_tasks.*": {"queue": "queue.reports"},
    },

    # Prioridades
    task_queue_max_priority=10,
    task_default_priority=5,

    # Expiración de resultados
    result_expires=3600,  # 1 hora
)
