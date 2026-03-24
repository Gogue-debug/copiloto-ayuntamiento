# CLAUDE.md — Copiloto Administrativo para Ayuntamientos

## Stack
Backend: Python 3.12 + FastAPI | Frontend: Next.js 15 | DB: PostgreSQL 16 + pgvector
IA: Claude claude-sonnet-4-6 via SDK `anthropic` | Queue: Celery + Redis | Storage: MinIO
Auth: Keycloak | Proxy: Traefik | Monorepo: Turborepo + pnpm

## Comandos de desarrollo

### Stack completo local
```bash
docker compose -f infra/docker/docker-compose.yml up -d
```

### Backend (desde apps/api/)
```bash
uv run uvicorn src.main:app --reload --port 8000
uv run alembic upgrade head
uv run pytest
```

### Frontend (desde apps/web/)
```bash
pnpm dev        # http://localhost:3000
pnpm build
pnpm lint
```

### Todos los tests
```bash
turbo test
```

### Ingestar knowledge base para un municipio
```bash
uv run python scripts/seed_knowledge_base.py --municipio-slug <slug> --path knowledge-base/template/
```

### Crear nuevo municipio (tenant)
```bash
uv run python scripts/create_municipality.py --name "Ayuntamiento de X" --slug "x"
```

### Generar tipos TypeScript desde OpenAPI
```bash
bash scripts/generate_openapi_types.sh
```

---

## Estructura del proyecto
- `apps/api/` — FastAPI backend + Celery workers
- `apps/web/` — Next.js 15 frontend (ciudadano + backoffice + admin)
- `apps/worker/` — Contenedor Celery separado (misma base de código que api)
- `infra/` — Docker Compose, Traefik, PostgreSQL, Keycloak, Prometheus, Grafana
- `knowledge-base/template/` — Documentos semilla por municipio (NUNCA commitear datos reales de ciudadanos)
- `scripts/` — Scripts operacionales (onboarding, migraciones, exportación cumplimiento)
- `docs/` — Arquitectura, integraciones, cumplimiento ENS, runbooks

---

## Convenciones críticas

### Multi-tenancy (LEER PRIMERO)
- TODA consulta a DB debe incluir `municipio_id`
- El middleware `tenant.py` inyecta el tenant via variable de sesión PostgreSQL: `SET app.current_municipio_id`
- Nunca escribir SQL sin `WHERE municipio_id = current_setting('app.current_municipio_id')::uuid`
- Los schemas Pydantic incluyen `municipio_id` a nivel de servicio, NO en la capa API
- MinIO: prefijo de objetos siempre `{municipio_id}/{año}/{mes}/{archivo}`

### Humano en el Bucle — Ley 39/2015 (OBLIGATORIO)
- Los agentes NUNCA escriben directamente en expedientes ni activan actos administrativos
- Los agentes devuelven `AgentResponse` → el servicio lo persiste como DRAFT
- Solo transiciones iniciadas por el staff pueden avanzar el estado más allá de `PENDING_REVIEW`
- State machine obligatoria: `AI_DRAFT → PENDING_REVIEW → APPROVED → SIGNED`
- El estado machine se aplica con CHECK constraints en PostgreSQL (no solo en código)

### Patrón de Agentes
- Todos los agentes extienden `BaseAgent` en `apps/api/src/agents/base.py`
- Los agentes reciben un `AgentContext` dataclass; son stateless y testeables
- Usar SDK `anthropic` directamente — NUNCA langchain ni otros wrappers de agentes
- Los tools (tool_use) son funciones Python tipadas en `apps/api/src/agents/tools/`
- System prompts en `apps/api/src/agents/prompts/{agent_name}.jinja2` (con variables por municipio)
- Los agentes NO acceden directamente a la DB; lo hacen via servicios recibidos en el contexto

### RGPD — Reglas PII (CRÍTICO)
- NUNCA registrar DNI, nombre completo ni teléfono en logs de aplicación
- Usar siempre `audit_svc.py` para acciones sobre datos sensibles
- Ciudadanos identificados por `session_token` en logs, NUNCA por nombre o DNI
- El middleware `rgpd.py` limpia automáticamente PII de los logs antes de escribirlos

### Lenguaje administrativo español
- Todas las cadenas de usuario en español formal (tratamiento de usted)
- Usar nomenclatura oficial española:
  - "Licencia de obra menor" (NO "building permit")
  - "Vado permanente" (NO "driveway permit")
  - "Ocupación de vía pública" (NO "street use permit")
  - "Padrón municipal" (NO "census register")

### Estilo de código Python
- Linter/formatter: `ruff` con `line-length = 100`
- Type checking: `mypy` en modo strict
- Timeout explícito en TODAS las llamadas a Claude API: 30s para chat, 120s para batch
- Todas las llamadas a APIs externas envueltas en try/except con log estructurado

### Estilo de código TypeScript
- `eslint` + `prettier`
- TypeScript en modo strict
- Tipos generados desde OpenAPI en `apps/web/src/types/` (ejecutar `generate_openapi_types.sh`)

---

## Variables de entorno requeridas
Ver `.env.example` para la lista completa. **Nunca commitear `.env`.**

Mínimo para desarrollo:
```
ANTHROPIC_API_KEY       # Clave API de Anthropic
DATABASE_URL            # PostgreSQL connection string
REDIS_URL               # Redis connection string
MINIO_ENDPOINT          # MinIO endpoint
MINIO_ACCESS_KEY
MINIO_SECRET_KEY
KEYCLOAK_URL
KEYCLOAK_REALM
KEYCLOAK_CLIENT_SECRET
```

---

## Uso de Claude API
- **Modelo**: `claude-sonnet-4-6` para todos los agentes
- **Temperature**: `0.1` para redacción de resoluciones (consistencia legal), `0.7` para FAQ ciudadano (conversación natural)
- **Streaming**: `stream=True` en endpoints de chat ciudadano; modo batch en OCR/informes
- **Tokens**: Registrar `input_tokens` y `output_tokens` en `audit_log` para facturación por municipio
- **Rate limiting**: Tareas Celery respetan rate limits de Anthropic via token bucket en Redis

---

## Flujos de datos clave

### Chat ciudadano
```
Ciudadano → POST /v1/chat/message
  → TenantMiddleware (municipio_id desde subdominio)
  → ChatService (carga historial desde Redis)
  → CitizenFAQAgent → Claude API
      → tool: search_municipal_knowledge() → pgvector
  → Persiste en PostgreSQL (anonimizado)
  → SSE stream al cliente
```

### OCR facturas
```
Staff sube PDF → MinIO → Celery task
  → Google Document AI (OCR)
  → OCRExtractorAgent → Claude (extrae campos estructurados)
  → Invoice{status: PENDING_REVIEW} en DB
  → Staff revisa en InvoiceReviewTable → Confirma → APPROVED
  → Export Excel via openpyxl
```

### Borrador de resolución
```
Staff crea expediente → POST /v1/resolutions/draft
  → Celery task → ResolutionDrafterAgent → Claude API
      → tool: get_regulation_context() → pgvector (ordenanzas)
      → tool: get_template() → plantilla Word
      → tool: get_precedents() → resoluciones anteriores similares
  → Resolution{status: AI_DRAFT}
  → Staff revisa en ResolutionEditor (diff view)
  → Aprueba → APPROVED → Firma digital → SIGNED
```

---

## Testing
- Tests unitarios: obligatorios para toda lógica de agentes (mock Claude API con cassettes)
- Tests de integración: obligatorios para todos los endpoints
- Cobertura mínima: 80% en `agents/` y `services/`
- Tests de carga: Locust antes de cada go-live de fase
- Test de aislamiento tenant: verificar que municipio_id_A no devuelve datos de municipio_id_B
