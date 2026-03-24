-- =============================================================================
-- Copiloto Administrativo — Inicialización PostgreSQL
-- Se ejecuta automáticamente al crear el contenedor por primera vez
-- =============================================================================

-- Extensiones necesarias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";        -- pgvector: búsqueda semántica
CREATE EXTENSION IF NOT EXISTS "pgcrypto";      -- cifrado columnas PII

-- =============================================================================
-- Row Level Security (RLS) — Multi-tenancy
-- Se activa en cada tabla con municipio_id.
-- El middleware FastAPI establece: SET app.current_municipio_id = '<uuid>'
-- =============================================================================

-- Función auxiliar para obtener el municipio_id del contexto de sesión
CREATE OR REPLACE FUNCTION current_municipio_id() RETURNS uuid AS $$
  SELECT current_setting('app.current_municipio_id', true)::uuid;
$$ LANGUAGE sql STABLE;

-- =============================================================================
-- Tabla: municipios (tenants)
-- =============================================================================
CREATE TABLE IF NOT EXISTS municipios (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre          text NOT NULL,
    slug            text NOT NULL UNIQUE,          -- e.g. "alcazar-san-juan"
    dominio         text,                          -- e.g. "alcazar.copiloto.es"
    config          jsonb NOT NULL DEFAULT '{}',   -- configuración por municipio
    activo          boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- =============================================================================
-- Tabla: conversaciones (sesiones de chat con ciudadanos)
-- =============================================================================
CREATE TABLE IF NOT EXISTS conversaciones (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    municipio_id    uuid NOT NULL REFERENCES municipios(id),
    session_token   text NOT NULL,                 -- identificador anónimo del ciudadano
    canal           text NOT NULL CHECK (canal IN ('web', 'whatsapp', 'email', 'telefono')),
    iniciada_at     timestamptz NOT NULL DEFAULT now(),
    ultima_at       timestamptz NOT NULL DEFAULT now(),
    metadata        jsonb NOT NULL DEFAULT '{}'    -- sin PII
);

ALTER TABLE conversaciones ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_conversaciones ON conversaciones
    USING (municipio_id = current_municipio_id());

-- =============================================================================
-- Tabla: mensajes (mensajes individuales dentro de una conversación)
-- =============================================================================
CREATE TABLE IF NOT EXISTS mensajes (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    municipio_id    uuid NOT NULL REFERENCES municipios(id),
    conversacion_id uuid NOT NULL REFERENCES conversaciones(id),
    rol             text NOT NULL CHECK (rol IN ('user', 'assistant', 'system')),
    contenido       text NOT NULL,
    tokens_input    integer,
    tokens_output   integer,
    created_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE mensajes ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_mensajes ON mensajes
    USING (municipio_id = current_municipio_id());

-- =============================================================================
-- Tabla: expedientes
-- =============================================================================
CREATE TABLE IF NOT EXISTS expedientes (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    municipio_id    uuid NOT NULL REFERENCES municipios(id),
    numero          text,                          -- número de expediente oficial
    tipo_tramite    text NOT NULL,                 -- e.g. "obra_menor", "vado", "padron"
    estado          text NOT NULL DEFAULT 'borrador'
                    CHECK (estado IN ('borrador', 'presentado', 'en_tramite', 'subsanacion', 'resuelto', 'archivado')),
    solicitante_ref text,                          -- referencia cifrada al ciudadano
    datos           jsonb NOT NULL DEFAULT '{}',   -- datos del expediente (PII cifrada externamente)
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE expedientes ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_expedientes ON expedientes
    USING (municipio_id = current_municipio_id());

-- =============================================================================
-- Tabla: resoluciones (borradores generados por IA + state machine)
-- =============================================================================
CREATE TABLE IF NOT EXISTS resoluciones (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    municipio_id    uuid NOT NULL REFERENCES municipios(id),
    expediente_id   uuid NOT NULL REFERENCES expedientes(id),
    tipo            text NOT NULL,                 -- "resolucion", "informe", "requerimiento"
    estado          text NOT NULL DEFAULT 'ai_draft'
                    CHECK (estado IN ('ai_draft', 'pending_review', 'approved', 'signed', 'rejected')),
    contenido_ia    text NOT NULL,                 -- borrador generado por Claude
    contenido_final text,                          -- texto final tras revisión humana
    citas           jsonb NOT NULL DEFAULT '[]',   -- artículos de ordenanza citados
    confianza_ia    numeric(3,2),                  -- 0.00 - 1.00
    flags_revision  jsonb NOT NULL DEFAULT '[]',   -- aspectos que requieren revisión humana
    aprobado_por    text,                          -- referencia al funcionario que aprobó
    aprobado_at     timestamptz,
    firmado_por     text,                          -- referencia al firmante (Secretario/Alcalde)
    firmado_at      timestamptz,
    firma_hash      text,                          -- hash del documento firmado
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    -- Restricciones del state machine: no se puede saltar estados
    CONSTRAINT resolucion_aprobacion_requiere_revision
        CHECK (
            estado NOT IN ('approved', 'signed') OR aprobado_por IS NOT NULL
        ),
    CONSTRAINT resolucion_firma_requiere_aprobacion
        CHECK (
            estado != 'signed' OR (aprobado_por IS NOT NULL AND firmado_por IS NOT NULL)
        )
);

ALTER TABLE resoluciones ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_resoluciones ON resoluciones
    USING (municipio_id = current_municipio_id());

-- =============================================================================
-- Tabla: facturas_ocr (datos extraídos por el agente OCR)
-- =============================================================================
CREATE TABLE IF NOT EXISTS facturas_ocr (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    municipio_id    uuid NOT NULL REFERENCES municipios(id),
    lote_id         uuid NOT NULL,                 -- agrupa facturas de un mismo upload
    fichero_ref     text NOT NULL,                 -- clave MinIO del fichero original
    estado          text NOT NULL DEFAULT 'pending_review'
                    CHECK (estado IN ('pending_review', 'approved', 'rejected')),
    -- Campos extraídos por OCR + Claude
    nif_proveedor   text,
    nombre_proveedor text,
    fecha_factura   date,
    numero_factura  text,
    concepto        text,
    base_imponible  numeric(12,2),
    iva_porcentaje  numeric(5,2),
    iva_importe     numeric(12,2),
    total           numeric(12,2),
    -- Calidad y alertas
    confianza_ocr   numeric(3,2),
    alertas         jsonb NOT NULL DEFAULT '[]',   -- discrepancias detectadas
    datos_crudos    jsonb NOT NULL DEFAULT '{}',   -- output bruto de Document AI
    aprobado_por    text,
    aprobado_at     timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE facturas_ocr ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_facturas_ocr ON facturas_ocr
    USING (municipio_id = current_municipio_id());

-- =============================================================================
-- Tabla: documentos_kb (knowledge base — fragmentos para búsqueda semántica)
-- =============================================================================
CREATE TABLE IF NOT EXISTS documentos_kb (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    municipio_id    uuid NOT NULL REFERENCES municipios(id),
    fuente_tipo     text NOT NULL CHECK (fuente_tipo IN ('ordenanza', 'faq', 'procedimiento', 'acta', 'bando', 'plantilla')),
    fuente_nombre   text NOT NULL,                 -- nombre del documento original
    fuente_anyo     integer,
    seccion         text,                          -- título de sección
    pagina          integer,
    chunk_index     integer NOT NULL DEFAULT 0,
    contenido       text NOT NULL,                 -- texto del fragmento
    embedding       vector(1536),                  -- embedding (OpenAI text-embedding-3-small)
    metadata        jsonb NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE documentos_kb ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_documentos_kb ON documentos_kb
    USING (municipio_id = current_municipio_id());

-- Índice HNSW para búsqueda vectorial eficiente (cosine similarity)
CREATE INDEX IF NOT EXISTS idx_documentos_kb_embedding
    ON documentos_kb USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Índice de texto completo (búsqueda híbrida)
CREATE INDEX IF NOT EXISTS idx_documentos_kb_fts
    ON documentos_kb USING gin (to_tsvector('spanish', contenido));

-- =============================================================================
-- Tabla: audit_log (trazabilidad ENS — append-only con hash chain)
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id              bigserial PRIMARY KEY,
    municipio_id    uuid REFERENCES municipios(id),
    timestamp       timestamptz NOT NULL DEFAULT now(),
    accion          text NOT NULL,                 -- e.g. "resolucion.aprobada", "factura.rechazada"
    actor_ref       text,                          -- referencia al usuario (NO PII directa)
    recurso_tipo    text,                          -- "resolucion", "factura", "expediente"
    recurso_id      uuid,
    detalles        jsonb NOT NULL DEFAULT '{}',   -- contexto de la acción (sin PII)
    ip_hash         text,                          -- hash de la IP (no la IP directa — RGPD)
    hash_previo     text,                          -- hash del registro anterior (integridad)
    hash_actual     text                           -- SHA-256 de (id + timestamp + accion + hash_previo)
);

-- El audit_log NO tiene RLS — todos los tenants pueden leer su propio log
-- pero se filtra por aplicación. No tiene UPDATE ni DELETE por diseño.
CREATE INDEX IF NOT EXISTS idx_audit_log_municipio
    ON audit_log (municipio_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_recurso
    ON audit_log (recurso_tipo, recurso_id);

-- =============================================================================
-- Índices adicionales de rendimiento
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_conversaciones_municipio_session
    ON conversaciones (municipio_id, session_token);

CREATE INDEX IF NOT EXISTS idx_expedientes_municipio_tipo
    ON expedientes (municipio_id, tipo_tramite, estado);

CREATE INDEX IF NOT EXISTS idx_resoluciones_estado
    ON resoluciones (municipio_id, estado, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_facturas_lote
    ON facturas_ocr (municipio_id, lote_id, estado);
