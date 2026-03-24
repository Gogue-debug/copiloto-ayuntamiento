"""Modelo SQLAlchemy: Expediente administrativo."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class Expediente(Base):
    __tablename__ = "expedientes"

    __table_args__ = (
        CheckConstraint(
            "estado IN ('borrador', 'presentado', 'en_tramite', 'subsanacion', 'resuelto', 'archivado')",
            name="ck_expediente_estado_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    municipio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("municipios.id"), nullable=False
    )
    numero: Mapped[str | None] = mapped_column(String, nullable=True)
    tipo_tramite: Mapped[str] = mapped_column(String, nullable=False)
    # e.g. "obra_menor", "vado", "ocupacion_via", "contrato_menor", "padron"

    estado: Mapped[str] = mapped_column(String, nullable=False, default="borrador")
    solicitante_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    # Referencia cifrada al ciudadano — sin PII directa en este campo
    datos: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # PII cifrada externamente (pgcrypto) en campos sensibles

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Expediente numero={self.numero!r} tipo={self.tipo_tramite!r}>"
