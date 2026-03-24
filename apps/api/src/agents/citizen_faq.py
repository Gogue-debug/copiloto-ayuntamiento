"""
Agente: CitizenFAQ

Responde preguntas de ciudadanos sobre trámites municipales usando RAG
(Retrieval-Augmented Generation) sobre la knowledge base del ayuntamiento.

Características:
- Responde SOLO con información de la knowledge base del municipio
- Cita la fuente (ordenanza, procedimiento, FAQ) de cada respuesta
- Deriva a atención humana si la pregunta supera su contexto
- Ofrece próximo paso: cita previa, documentos necesarios
- NUNCA toma decisiones administrativas (solo informa)
"""
import time
from typing import Any

import structlog

from src.agents.base import AgentContext, AgentResponse, BaseAgent, ToolDefinition
from src.services.embedding_svc import search_knowledge_base

logger = structlog.get_logger()


class CitizenFAQAgent(BaseAgent):
    """
    Agente de atención al ciudadano: responde consultas sobre trámites
    basándose en la knowledge base del ayuntamiento.
    """

    @property
    def name(self) -> str:
        return "citizen_faq"

    @property
    def temperature(self) -> float:
        return 0.7  # Conversacional y natural

    @property
    def tools(self) -> list[ToolDefinition]:
        return [
            {
                "name": "buscar_informacion_municipal",
                "description": (
                    "Busca información en la knowledge base del ayuntamiento sobre trámites, "
                    "ordenanzas, horarios, requisitos y procedimientos. "
                    "Usar SIEMPRE antes de responder cualquier pregunta del ciudadano."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "consulta": {
                            "type": "string",
                            "description": "La pregunta o tema a buscar, en lenguaje natural",
                        }
                    },
                    "required": ["consulta"],
                },
            },
            {
                "name": "obtener_checklist_documentacion",
                "description": (
                    "Obtiene la lista de documentos necesarios para un trámite específico. "
                    "Usar cuando el ciudadano pregunta qué documentos necesita llevar."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "tipo_tramite": {
                            "type": "string",
                            "description": (
                                "Tipo de trámite: obra_menor, vado, ocupacion_via, "
                                "padron, contrato_menor, etc."
                            ),
                        }
                    },
                    "required": ["tipo_tramite"],
                },
            },
        ]

    def system_prompt(self, context: AgentContext) -> str:
        nombre_municipio = context.municipio_nombre
        return f"""Eres el asistente virtual del {nombre_municipio}. Tu función es ayudar \
a los ciudadanos con información sobre trámites, servicios municipales y procedimientos \
administrativos.

REGLAS ESTRICTAS:
1. Responde ÚNICAMENTE con información obtenida de la knowledge base del ayuntamiento \
(usa la herramienta buscar_informacion_municipal antes de responder).
2. Si la información no está en la knowledge base, di exactamente: \
"No dispongo de esa información en este momento. Le recomiendo contactar con el \
Ayuntamiento en horario de atención al público."
3. NUNCA inventes datos, plazos, tasas ni requisitos.
4. NUNCA tomes decisiones administrativas ni des interpretaciones jurídicas vinculantes.
5. Siempre usa tratamiento de usted y lenguaje formal pero cercano.
6. Al final de cada respuesta, ofrece el siguiente paso concreto (cita, documento, teléfono).
7. Si detectas urgencia social (persona en situación vulnerable), incluye: \
"Si su situación requiere atención urgente, puede contactar con los Servicios Sociales \
municipales."

FORMATO DE RESPUESTA:
- Respuesta directa y clara a la pregunta
- Si aplica: lista de documentos necesarios
- Siguiente paso recomendado
- Fuente citada (nombre del documento de la knowledge base)

Municipio: {nombre_municipio}
Canal: {context.canal}"""

    async def run(self, context: AgentContext) -> AgentResponse:
        """
        Ejecuta el agente: busca en la KB y genera respuesta con Claude.
        Implementa el ciclo tool_use de Anthropic.
        """
        start = time.monotonic()

        # Construir historial de mensajes
        messages: list[dict[str, Any]] = list(context.conversation_history)
        messages.append({"role": "user", "content": context.user_input})

        # Ciclo agentic (puede iterar hasta que Claude no llame más tools)
        citations: list[dict[str, Any]] = []
        escalate = False
        max_iterations = 5

        for iteration in range(max_iterations):
            response = await self._call_claude(context, messages)

            # Verificar si Claude quiere usar herramientas
            if response.stop_reason == "tool_use":
                # Procesar cada tool call
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    result = await self._handle_tool(block.name, block.input, context)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result.get("content", ""),
                    })

                    # Acumular citas
                    if "citations" in result:
                        citations.extend(result["citations"])

                # Añadir respuesta de Claude y resultados al historial
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

            elif response.stop_reason == "end_turn":
                # Respuesta final
                content = self._extract_text(response)
                escalate = self._should_escalate(content)
                duration_ms = int((time.monotonic() - start) * 1000)

                return self._build_response(
                    content=content,
                    response=response,
                    duration_ms=duration_ms,
                    citations=citations,
                    escalate_to_human=escalate,
                    human_review_flags=(
                        ["Derivar a atención humana"] if escalate else []
                    ),
                )
            else:
                # max_tokens u otro stop_reason inesperado
                break

        # Si llegamos aquí, se agotaron las iteraciones
        duration_ms = int((time.monotonic() - start) * 1000)
        return AgentResponse(
            content=(
                "Disculpe, no he podido procesar su consulta correctamente. "
                "Por favor, contacte con el Ayuntamiento directamente."
            ),
            agent_name=self.name,
            model=self._get_model_name(),
            escalate_to_human=True,
            duration_ms=duration_ms,
        )

    async def _handle_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        """Ejecuta una herramienta y devuelve el resultado."""

        if tool_name == "buscar_informacion_municipal":
            return await self._tool_buscar(tool_input["consulta"], context)

        elif tool_name == "obtener_checklist_documentacion":
            return await self._tool_checklist(tool_input["tipo_tramite"], context)

        return {"content": f"Herramienta {tool_name!r} no disponible."}

    async def _tool_buscar(
        self, consulta: str, context: AgentContext
    ) -> dict[str, Any]:
        """Busca en la knowledge base del municipio."""
        if not context.db_session:
            return {"content": "Base de conocimiento no disponible en este momento."}

        results = await search_knowledge_base(
            session=context.db_session,
            municipio_id=context.municipio_id,
            query=consulta,
            limit=5,
        )

        if not results:
            return {
                "content": (
                    "No se ha encontrado información específica sobre este tema "
                    "en la base de conocimiento del ayuntamiento."
                ),
                "citations": [],
            }

        # Formatear resultados para Claude
        formatted = []
        citations = []
        for r in results:
            fuente = f"{r['fuente_nombre']}"
            if r.get("fuente_anyo"):
                fuente += f" ({r['fuente_anyo']})"
            if r.get("seccion"):
                fuente += f" — {r['seccion']}"

            formatted.append(f"[Fuente: {fuente}]\n{r['contenido']}")
            citations.append({
                "fuente": fuente,
                "tipo": r["fuente_tipo"],
                "relevancia": r["score"],
            })

        return {
            "content": "\n\n---\n\n".join(formatted),
            "citations": citations,
        }

    async def _tool_checklist(
        self, tipo_tramite: str, context: AgentContext
    ) -> dict[str, Any]:
        """Obtiene el checklist de documentos de un trámite."""
        if not context.db_session:
            return {"content": "Información de trámites no disponible en este momento."}

        # Buscar el procedimiento específico en la KB
        results = await search_knowledge_base(
            session=context.db_session,
            municipio_id=context.municipio_id,
            query=f"documentación requerida {tipo_tramite} requisitos documentos",
            limit=3,
        )

        if results:
            content = f"Documentación para '{tipo_tramite}':\n\n"
            content += "\n\n".join(r["contenido"] for r in results)
            return {"content": content, "citations": [{"fuente": r["fuente_nombre"], "tipo": r["fuente_tipo"], "relevancia": r["score"]} for r in results]}

        return {
            "content": (
                f"No se encontró información específica sobre la documentación "
                f"para el trámite '{tipo_tramite}'. "
                "Consulte en las oficinas municipales o en la web del ayuntamiento."
            )
        }

    @staticmethod
    def _should_escalate(content: str) -> bool:
        """Detecta si la respuesta indica que se debe derivar a atención humana."""
        escalation_phrases = [
            "no dispongo de esa información",
            "contacte con el ayuntamiento",
            "le recomiendo que acuda",
            "no puedo responder",
            "situación compleja",
            "requiere asesoramiento",
        ]
        content_lower = content.lower()
        return any(phrase in content_lower for phrase in escalation_phrases)

    def _get_model_name(self) -> str:
        from src.config import get_settings
        return get_settings().claude_model
