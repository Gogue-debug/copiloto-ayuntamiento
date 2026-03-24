"""
Modelo SQLAlchemy: Resolución (borrador generado por IA).

State machine (Ley 39/2015 — humano en el bucle):
  AI_DRAFT → PENDING_REVIEW → APPROVED → SIGNED
                           ↘ REJECTED

Las transiciones se validan tanto en código (service layer) como en DB (CHECK constraints).
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class ResolucionEstado:
    """Constantes para el state machine de resoluciones."""
    AI_DRAFT = "ai_draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    SIGNED = "signed"
    REJECTED = "rejected"

    VALID_STATES = {AI_DRAFT, PENDING_REVIEW, APPROVED, SIGNED, REJECTED}

    # Transiciones permitidas: {estado_actual: [estados_destino_permitidos]}
    TRANSITIONS: dict[str, list[str]] = {
        AI_DRAFT: [PENDING_REVIEW, REJECTED],
        PENDING_REVIEW: [APPROVED, REJECTED, AI_DRAFT],  # puede volver a draft si se edita
        APPROVED: [SIGNED, PENDING_REVIEW],              # puede re-revisar si se detecta error
        SIGNED: [],                                       # estado final — no hay vuelta atrás
        REJECTED: [],                                     # estado final
    }

    @classmethod
    def can_transition(cls, from_state: str, to_state: str) -> bool:
        return to_state in cls.TRANSITIONS.get(from_state, [])


class Resolucion(Base):
    __tablename__ = "resoluciones"

    __table_args__ = (
        CheckConstraint(
            "estado IN ('ai_draft', 'pending_review', 'approved', 'signed', 'rejected')",
            name="ck_resolucion_estado_valid",
        ),
        # No puede estar aprobada sin un aprobador
        CheckConstraint(
            "estado NOT IN ('approved', 'signed') OR aprobado_por IS NOT NULL",
            name="ck_resolucion_aprobacion_requiere_actor",
        ),
        # No puede estar firmada sin aprobación y firmante
        CheckConstraint(
            "estado != 'signed' OR (aprobado_por IS NOT NULL AND firmado_por IS NOT NULL)",
            name="ck_resolucion_firma_requiere_aprobacion",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    municipio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("municipios.id"), nullable=False
    )
    expediente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes.id"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(
        String,
        nullable=False,
        # "resolucion" | "informe" | "requerimiento"
    )
    estado: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=ResolucionEstado.AI_DRAFT,
    )

    # Contenido generado por IA
    contenido_ia: Mapped[str] = mapped_column(Text, nullable=False)

    # Contenido final tras revisión humana (puede ser igual o diferente al de IA)
    contenido_final: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadatos de calidad IA
    citas: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    confianza_ia: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    flags_revision: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)

    # Trazabilidad de aprobación (Ley 39/2015)
    aprobado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    aprobado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Trazabilidad de firma digital
    firmado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    firmado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    firma_hash: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def transition_to(self, new_state: str, actor_ref: str | None = None) -> None:
        """
        Realiza una transición de estado validada.
        Lanza ValueError si la transición no está permitida.
        """
        if not ResolucionEstado.can_transition(self.estado, new_state):
            raise ValueError(
                f"Transición no permitida: {self.estado!r} → {new_state!r}. "
                f"Transiciones válidas desde {self.estado!r}: "
                f"{ResolucionEstado.TRANSITIONS.get(self.estado, [])}"
            )

        if new_state == ResolucionEstado.APPROVED and not actor_ref:
            raise ValueError("Se requiere actor_ref para aprobar una resolución")

        if new_state == ResolucionEstado.SIGNED and not actor_ref:
            raise ValueError("Se requiere actor_ref para firmar una resolución")

        self.estado = new_state

    def __repr__(self) -> str:
        return f"<Resolucion id={self.id} tipo={self.tipo!r} estado={self.estado!r}>"
