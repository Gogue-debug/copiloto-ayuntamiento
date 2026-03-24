"""
Modelo SQLAlchemy: AuditLog — trazabilidad ENS (append-only con hash chain).

IMPORTANTE:
- Este modelo NO tiene UPDATE ni DELETE (enforced en la capa de servicio).
- Cada registro encadena el hash del anterior para detectar manipulaciones.
- No contiene PII directa: actores identificados por referencias, IPs por hash.
"""
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    municipio_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("municipios.id"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    accion: Mapped[str] = mapped_column(String, nullable=False)
    # e.g. "resolucion.aprobada", "factura.rechazada", "chat.escalado"

    actor_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    # Referencia al usuario (NO PII directa — usar ID de Keycloak o hash de sesión)

    recurso_tipo: Mapped[str | None] = mapped_column(String, nullable=True)
    # "resolucion" | "factura" | "expediente" | "conversacion" | "conocimiento"

    recurso_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    detalles: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Contexto adicional — sin PII

    ip_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    # Hash SHA-256 de la IP (no la IP directa — RGPD art. 25)

    hash_previo: Mapped[str | None] = mapped_column(String, nullable=True)
    # Hash del registro anterior (integridad de la cadena)

    hash_actual: Mapped[str | None] = mapped_column(String, nullable=True)
    # SHA-256 de (id + timestamp + accion + actor_ref + recurso_id + hash_previo)

    @classmethod
    def compute_hash(
        cls,
        id: int,
        timestamp: datetime,
        accion: str,
        actor_ref: str | None,
        recurso_id: uuid.UUID | None,
        hash_previo: str | None,
    ) -> str:
        """Calcula el hash de este registro para la cadena de integridad."""
        payload = json.dumps(
            {
                "id": id,
                "timestamp": timestamp.isoformat(),
                "accion": accion,
                "actor_ref": actor_ref,
                "recurso_id": str(recurso_id) if recurso_id else None,
                "hash_previo": hash_previo,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} accion={self.accion!r}>"
