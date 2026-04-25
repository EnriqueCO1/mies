"""
AI Service - wraps the Claude + document search logic.
Adapted from hybrid_query.py for use with FastAPI.

Fully async: uses anthropic.AsyncAnthropic + openai.AsyncOpenAI, and runs
Supabase RPCs concurrently via asyncio.gather (the supabase-py sync client
is wrapped with asyncio.to_thread so multiple match_* calls don't serialize).
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Union
import anthropic
from openai import AsyncOpenAI
from supabase import Client
from app.config import settings
from app.services.files import markdown_to_docx_bytes, markdown_to_bytes

logger = logging.getLogger(__name__)


class AIService:
    """Claude conversation with architecture normativa access."""

    def __init__(self, supabase: Client):
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to backend/.env."
            )
        # OpenAI is optional — only used for doc search embeddings.
        # If it's missing, we still let chat run (search just returns []).
        self.openai_client = (
            AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            if settings.OPENAI_API_KEY
            else None
        )
        self.anthropic_client = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
        )
        self.supabase = supabase

    # Mime types we can hand to the Anthropic Files API for file_id-based
    # references. Everything else (text/plain, text/markdown) still flows
    # inline through build_claude_content_blocks.
    _FILES_API_MIMES = frozenset({
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/gif",
        "image/webp",
    })

    async def upload_attachment(
        self,
        filename: str,
        mime: str,
        data: bytes,
    ) -> Optional[str]:
        """
        Upload an attachment to Anthropic's Files API so subsequent turns
        can reference it by `file_id` instead of re-inlining base64.
        Returns the file_id on success, or None if:
          - the mime isn't something the Files API handles (text, etc.)
          - the upload fails (Anthropic down, over quota, etc.)
        Never raises — a failed upload falls back to inline base64.
        """
        if mime not in self._FILES_API_MIMES:
            return None
        try:
            import io as _io
            uploaded = await self.anthropic_client.beta.files.upload(
                file=(filename, _io.BytesIO(data), mime),
            )
            logger.info(
                f"Anthropic Files API upload: {filename} ({len(data):,} bytes) "
                f"→ {uploaded.id}"
            )
            return uploaded.id
        except Exception as e:
            logger.warning(
                f"Anthropic Files API upload failed for {filename!r}: {e}. "
                f"Falling back to inline base64."
            )
            return None

    def _log_cache_usage(self, label: str, response: Any) -> None:
        """
        Emit prompt-cache stats for a Claude response. Useful to confirm
        that our cache_control markers are actually producing hits.
        Reads `response.usage` defensively — older SDK versions may not
        carry the cache fields.
        """
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        created = getattr(usage, "cache_creation_input_tokens", 0) or 0
        read = getattr(usage, "cache_read_input_tokens", 0) or 0
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        # NOTE: WARNING level so it survives the default uvicorn logging
        # config. Demote to INFO once prompt caching is boring.
        logger.warning(
            f"[cache:{label}] input={input_tokens} output={output_tokens} "
            f"cache_created={created} cache_read={read}"
        )

    # Map municipio → dedicated PGOU table's match_* RPC. Keys are
    # lowercased/ASCII-folded so comparisons are case- and accent-
    # insensitive ("Málaga" / "malaga" / "MALAGA" all route to the
    # same table).
    #
    # A project's municipio is mandatory (frontend enforces it on
    # intake), so we expect every chat turn to match exactly ONE entry
    # here. If the municipio isn't in this dict, the corpus simply
    # isn't covered — `_search_documents` returns empty and Claude
    # explicitly tells the architect so (see system prompt).
    _PGOU_RPC_BY_MUNICIPIO: Dict[str, str] = {
        # Costa del Sol + Málaga city
        "malaga":                   "match_pgou_malaga",
        "marbella":                 "match_pgou_marbella",
        "torremolinos":             "match_pgou_torremolinos",
        "fuengirola":               "match_pgou_fuengirola",
        "mijas":                    "match_pgou_mijas",
        "estepona":                 "match_pgou_estepona",
        "benalmadena":              "match_pgou_benalmadena",
        "alhaurin de la torre":     "match_pgou_alhaurin_de_la_torre",
        # Axarquía + east
        "nerja":                    "match_pgou_nerja",
        "rincon":                   "match_pgou_rincon",
        "rincon de la victoria":    "match_pgou_rincon",   # alias — official name
        "velez-malaga":             "match_pgou_velez_malaga",
        "velez malaga":             "match_pgou_velez_malaga",  # space alias
        # Interior
        "antequera":                "match_pgou_antequera",
    }

    @staticmethod
    def _normalise_municipio(value: Optional[str]) -> str:
        """Lowercase + strip Spanish accents for municipio key lookup."""
        if not value:
            return ""
        import unicodedata
        folded = unicodedata.normalize("NFD", value.strip())
        return "".join(c for c in folded if unicodedata.category(c) != "Mn").lower()

    async def _search_documents(
        self,
        query: str,
        subject: Optional[str] = None,
        level: Optional[str] = None,
        max_results: int = 8,
        category: Optional[str] = None,
        project_municipio: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search normativa chunks across the per-corpus RPCs, **in parallel**.

        After migration 001, each corpus lives in its own table with its
        own HNSW index and match_* RPC:

            category='pgou' + municipio='Málaga'   → match_pgou_malaga
            category='pgou' + municipio='Marbella' → match_pgou_marbella
            category='pgou' + no municipio         → both PGOU RPCs
            category='cte'                         → match_cte
            category='both' / None                 → PGOU (routed) + CTE

        All applicable RPCs now fire concurrently via asyncio.gather —
        a `category='both'` search drops from ~1.1-2s sequential to
        ~300-500ms (the slowest single call).

        The `subject` / `level` parameters are no longer honoured — the
        new RPCs don't take them — but the signature is kept so no
        caller needs to change.
        """
        if self.openai_client is None:
            logger.warning("OPENAI_API_KEY not set; skipping document search.")
            return []

        response = await self.openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=query,
        )
        query_embedding = response.data[0].embedding

        # Detect normative references → switch on keyword/tsvector search
        import re as _re
        has_article_ref = bool(_re.search(
            r"art[íi]culo\s+\d+|secci[oó]n\s+\d+|cap[íi]tulo\s+[IVXLCDM\d]+|t[íi]tulo\s+[IVXLCDM\d]+|db[-\s]?(?:se|si|sua|hs|hr|he)",
            query,
            _re.IGNORECASE,
        ))

        async def _call_rpc(rpc: str) -> List[Dict[str, Any]]:
            # supabase-py's .execute() is synchronous; wrap it in a thread so
            # multiple RPC calls don't block the event loop (and can genuinely
            # run concurrently under asyncio.gather).
            params: Dict[str, Any] = {
                "query_embedding": query_embedding,
                "match_count": max_results,
                "match_threshold": 0.25,
            }
            if has_article_ref:
                params["search_query"] = query

            def _run_sync() -> List[Dict[str, Any]]:
                try:
                    return self.supabase.rpc(rpc, params).execute().data or []
                except Exception as e:
                    logger.error(f"Search error ({rpc}): {e}")
                    return []

            return await asyncio.to_thread(_run_sync)

        # ── Corpus routing ────────────────────────────────────────
        # Strict: for PGOU we *only* search the project's municipio
        # table. If the project has no municipio (shouldn't happen —
        # it's mandatory on intake) OR the municipio isn't covered, we
        # return zero PGOU hits and Claude's system prompt instructs it
        # to tell the architect explicitly. We intentionally DO NOT
        # fall back to searching every PGOU table, because mixing
        # ordenanzas from the wrong municipality is worse than honestly
        # saying "not covered".
        rpcs: List[str] = []
        cat = (category or "both").lower()
        muni_key = self._normalise_municipio(project_municipio)

        if cat in ("pgou", "both"):
            if muni_key and muni_key in self._PGOU_RPC_BY_MUNICIPIO:
                rpcs.append(self._PGOU_RPC_BY_MUNICIPIO[muni_key])
            # else: no covered municipio → no PGOU search this turn.
            # Claude will see zero PGOU results and must say so.
        if cat in ("cte", "both"):
            rpcs.append("match_cte")
        if cat in ("loe", "both"):
            # LOE is national-level — always searched when the category
            # permits, regardless of municipio.
            rpcs.append("match_loe")

        # Fire every selected RPC concurrently.
        results = await asyncio.gather(*(_call_rpc(r) for r in rpcs))
        raw: List[Dict[str, Any]] = [row for batch in results for row in batch]

        # Dedup by (source_file, first 80 chars of content) and rank by
        # similarity, then cap at the caller's requested max_results.
        seen = set()
        merged: List[Dict[str, Any]] = []
        for doc in raw:
            key = (doc.get("source_file", ""), (doc.get("content") or "")[:80])
            if key in seen:
                continue
            seen.add(key)
            merged.append(doc)
        merged.sort(key=lambda d: d.get("similarity", 0), reverse=True)
        merged = merged[:max_results]

        return [
            {
                "content": doc["content"],
                "source": doc.get("source_file", ""),
                "source_bucket": doc.get("source_bucket", ""),
                "subject": doc.get("section_title") or "",
                "similarity": round(doc.get("similarity", 0), 3),
                "page_number": doc.get("page_number"),
            }
            for doc in merged
        ]

    async def chat_stream(
        self,
        message: Union[str, List[Dict[str, Any]]],
        conversation_history: List[Dict[str, str]] = None,
        user_profile: Optional[Dict] = None,
        project_metadata: Optional[Dict] = None,
        subject_filter: Optional[str] = None,
        level_filter: Optional[str] = None,
    ):
        """
        Streaming variant of chat. Yields event dicts:

          {"type": "text_delta",   "text": "..."}  — incremental tokens
          {"type": "tool_call",    "name": "..."}  — a tool is starting
          {"type": "tool_result",  "name": "..."}  — a tool just completed
          {"type": "final",        "response": ..., "sources": [...],
                                   "documents": [...], "tools_used": [...]}

        The `final` event always fires exactly once, at the end, and
        carries the same shape the non-streaming `chat()` method returns.
        """
        """
        Send a message to Claude with architecture normativa search +
        document creation.

        `message` can be either a plain string or a pre-built list of
        Claude content blocks (used when the user attached files).
        """

        messages = []
        if conversation_history:
            for msg in conversation_history:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        user_content = (
            message if isinstance(message, list) else [{"type": "text", "text": message}]
        )
        messages.append({"role": "user", "content": user_content})

        # Build system prompt with user + project context
        user_context = ""
        if user_profile:
            colegiado = user_profile.get("colegiado_number", "")
            user_context = f"""
Arquitecto:
- Nombre: {user_profile.get('name', 'Arquitecto')}
- Colegiado: {colegiado if colegiado else 'No indicado'}
"""

        project_context = ""
        if project_metadata:
            materials = ", ".join(project_metadata.get("main_materials") or []) or "No especificados"
            budget = project_metadata.get("estimated_budget")
            budget_str = f"{budget:,.0f} EUR" if budget else "No especificado"
            project_context = f"""
Proyecto actual:
- Dirección: {project_metadata.get('address', 'No especificada')}
- Municipio: {project_metadata.get('municipio') or 'No especificado'}
- Tipo de edificación: {project_metadata.get('building_type', 'No especificado')}
- Materiales principales: {materials}
- Presupuesto estimado: {budget_str}
- Ordenanza específica: {project_metadata.get('ordenanza') or 'No especificada'}

Nota: la superficie construida y el número de plantas se extraen automáticamente del bloque CATASTRAL de abajo cuando estén disponibles — no los pidas al arquitecto.
"""
            # Append catastro data if available
            catastro = project_metadata.get("catastro_data")
            if catastro and catastro.get("success"):
                sup_grafica = catastro.get("superficie_grafica") or "No disponible"
                sup_construida = catastro.get("superficie_construida") or "No disponible"
                num_plantas = catastro.get("num_plantas") or "No disponible"
                num_plantas_bajo = catastro.get("num_plantas_bajo_rasante") or "0"
                num_unidades = catastro.get("num_unidades") or "No disponible"
                num_viviendas = catastro.get("num_viviendas") or "No disponible"
                num_edificios = catastro.get("num_edificios")
                num_edificios_str = (
                    str(num_edificios) if num_edificios is not None else "1"
                )

                project_context += f"""
Datos catastrales (obtenidos de los servicios INSPIRE WFS del Catastro: CP + BU):

DATOS DESCRIPTIVOS DEL INMUEBLE:
- Referencia catastral: {catastro.get('ref_catastral', 'N/A')}
- Localización: {catastro.get('direccion_normalizada', 'N/A')}
- Código postal: {catastro.get('codigo_postal', 'N/A')}
- Provincia: {catastro.get('provincia', 'N/A')}
- Municipio: {catastro.get('municipio', 'N/A')}

PARCELA CATASTRAL (WFS CP):
- Superficie gráfica del solar: {sup_grafica} m²

EDIFICIO (WFS BU):
- Uso actual: {catastro.get('uso', 'N/A')} (código INSPIRE: {catastro.get('uso_codigo', 'N/A')})
- Año de construcción: {catastro.get('anio_construccion', 'N/A')}
- Superficie construida total: {sup_construida} m² ({catastro.get('superficie_construida_tipo', 'grossFloorArea')})
- Número de plantas sobre rasante: {num_plantas}
- Número de plantas bajo rasante: {num_plantas_bajo}
- Número de unidades del edificio: {num_unidades}
- Número de viviendas: {num_viviendas}
- Estado de la construcción: {catastro.get('estado_construccion', 'N/A')}
- Edificios en la parcela: {num_edificios_str}

URL Sede Electrónica: {catastro.get('sede_url', 'N/A')}
"""
                # Surface any partial failures
                warnings = catastro.get("warnings") or {}
                if warnings.get("parcel_error"):
                    project_context += f"\n⚠️ No se pudo obtener datos de parcela: {warnings['parcel_error']}\n"
                if warnings.get("building_error"):
                    project_context += f"\n⚠️ No se pudo obtener datos de edificio: {warnings['building_error']}\n"

                mismatch = catastro.get("mismatch_warning")
                if mismatch:
                    project_context += f"\n⚠️ AVISO: {mismatch}\n"
            elif catastro and not catastro.get("success"):
                project_context += f"""
Datos catastrales: No disponibles ({catastro.get('error', 'Error desconocido')})
"""

        # Stable system prompt — never mentions per-user / per-project data,
        # so the bytes are identical across every request and the API's
        # ephemeral cache (marker below) stays hot for the whole TTL.
        system_prompt_stable = """Eres Mies, un asistente de IA especializado en ayudar a arquitectos en España a elaborar Proyectos de Ejecución. Cuando te pregunten cómo te llamas o quién eres, responde que eres Mies — no digas Claude ni hagas referencia a otros modelos.

Tu ámbito de conocimiento:
- **Planes municipales de urbanismo** (PGOU, PGOM, NNSS, POM) — tienes acceso indexado a los planes de los siguientes municipios (provincia de Málaga):
    · Málaga
    · Marbella
    · Torremolinos
    · Fuengirola
    · Mijas
    · Estepona
    · Nerja
    · Benalmádena
    · Alhaurín de la Torre
    · Rincón de la Victoria
    · Vélez-Málaga
    · Antequera
  Cuando un proyecto tiene municipio, la búsqueda PGOU se limita automáticamente al plan de ESE municipio — nunca mezcles ordenanzas de municipios distintos. **Si el municipio del proyecto NO está en la lista anterior**, la búsqueda devolverá cero resultados de PGOU y debes decir explícitamente al arquitecto: "No tengo el PGOU de [municipio] indexado, no puedo citar su normativa urbanística municipal con exactitud. Puedo ayudarte con CTE, LOE o conocimiento general, o consulta directamente el ayuntamiento de [municipio]." Nunca improvises ordenanzas municipales.
- **Código Técnico de la Edificación (CTE)** — tienes acceso directo al contenido indexado de los seis Documentos Básicos (DB-SE, DB-SI, DB-SUA, DB-HS, DB-HR, DB-HE) y sus Documentos de Apoyo (DA). Úsalo SIEMPRE que la pregunta toque cualquier exigencia básica: seguridad estructural, incendios, utilización y accesibilidad, salubridad, ruido o ahorro energético.
- **LOE** — Ley 38/1999 de Ordenación de la Edificación. Tienes acceso indexado. Úsala para consultas sobre agentes de la edificación, licencias, garantías (decenal / trienal / anual), dirección facultativa, seguros obligatorios, responsabilidades, libro del edificio.
- **BCCA** — Banco de Coste de la Construcción de Andalucía. Base de precios oficial de referencia. Tienes acceso directo a su tabla con códigos, unidades, descripciones y precios en EUR. Es la base de precios POR DEFECTO para cualquier tabla, partida, medición, estimación o presupuesto — úsala a menos que el arquitecto pida explícitamente otra base (PREOC, BEDEC, precio propio, etc.).
- Instrucción de Hormigón Estructural (EHE-08)
- Normativa urbanística autonómica (LOUA para Andalucía)
- Catastro y referencias catastrales
- Normativa de accesibilidad
- Gestión de licencias y visados
- Presupuestos de ejecución material (PEM) y por contrata (PEC)

Tus funciones principales:
1. Asesoramiento técnico sobre normativa (CTE, LOE, EHE, urbanismo)
2. Redacción y revisión de memorias descriptivas, constructivas y de cumplimiento del CTE
3. Cálculos y verificaciones (DB-HE, DB-HR, DB-SI, etc.)
4. Generación de documentos del proyecto (memorias, anejos, pliegos)
5. Consulta de datos catastrales y urbanísticos

Reglas:
- Sé preciso y técnico. Cita artículos y secciones específicas cuando sea posible.
- **Cita SIEMPRE la fuente** de cada dato que uses:
    · Datos catastrales → `(Catastro, ref. XXXXXXX)`
    · Normativa PGOU → `(PGOU Málaga — [documento], p. N)`
    · Normativa CTE → `(CTE — DB-XX, apartado/tabla, p. N)`
    · Precios y partidas → `(BCCA, código XXXXXXX)`
  Nunca mezcles datos de distintas fuentes sin identificarlos. Si un dato proviene de conocimiento general (no de tus herramientas), márcalo claramente como "conocimiento general" para que el arquitecto pueda decidir si verificar.
- Si no estás seguro de un dato normativo, dilo claramente.
- Tono profesional pero directo. Sin rodeos.
- Si el arquitecto comete un error técnico, señálalo y explica por qué.
- Puedes hablar de cualquier tema, no solo arquitectura.

Tus herramientas:

1. Búsqueda de normativa (tool: search_normativa)
- Busca en dos corpus indexados:
    · **PGOU de Málaga** — Documento A (memorias, introducción, estudio económico-financiero) y Documento C (interactivo con marcadores). Category: `pgou`.
    · **CTE** — los seis Documentos Básicos (DB-SE, DB-SI, DB-SUA, DB-HS, DB-HR, DB-HE) y sus Documentos de Apoyo (DA-DB-xx-N). Category: `cte`.
- Usa el parámetro `category` para acotar la consulta cuando sepas a qué corpus pertenece: `pgou` para urbanismo municipal, `cte` para exigencias técnicas básicas, `both` (por defecto) cuando pueda estar en cualquiera.
- Aplica SIEMPRE la normativa encontrada al proyecto concreto del arquitecto (superficie, uso, año de construcción, zona PGOU) — no des respuestas genéricas si tienes datos del proyecto.
- No menciones que "estás buscando" — incorpora la información de forma natural.
- CITA SIEMPRE la fuente: nombre del documento, sección y página.

Cuándo usar search_normativa:
- Exigencias del CTE o cualquiera de sus DB (category='cte')
- Dudas puntuales aclaradas en algún Documento de Apoyo (category='cte')
- Normativa urbanística de Málaga, clasificación del suelo, ordenanzas, alturas, edificabilidad, usos permitidos, retranqueos (category='pgou')
- Requisitos EHE-08 y LOE (category='both')
- Cualquier referencia a artículos, secciones, capítulos o apéndices normativos

Cuándo NO usarla:
- Saludos y conversación general
- Preguntas que puedes responder bien sin consultar normativa
- Seguimiento de conversaciones donde ya tienes el contexto

2. Consulta de precios BCCA (tool: consultar_bcca)
- Consulta directa a la tabla del Banco de Coste de la Construcción de Andalucía (BCCA).
- Cada fila tiene: `codigo`, `unidad`, `descripcion`, `precio` (EUR).
- Úsala CADA VEZ que el arquitecto pida:
    · una tabla de precios, partidas o mediciones
    · coste unitario de un material, mano de obra o medio auxiliar
    · estimaciones de PEM / PEC
    · generación de presupuestos
  a menos que te indique explícitamente usar otra base (PREOC, BEDEC, precio propio, etc.).
- Puedes buscar por `query` (palabras clave sobre la descripción) o por `codigo` (exacto o prefijo).
- Cuando presentes resultados, mantén el formato tabular que te devuelve la herramienta e indica siempre `(BCCA, código XXXXXXX)` junto al precio.
- Si la BCCA no tiene una partida concreta, dilo claramente en lugar de inventar precios.

3. Consulta de datos del Catastro (tool: consultar_catastro)
- Ya detallada arriba — consulta vía los servicios INSPIRE WFS del Catastro.
- Cita con `(Catastro, ref. XXXXXXX)`.

4. Creación de documentos (tool: create_document)
- Cuando el arquitecto pida producir, redactar, generar o exportar un documento (memoria descriptiva, anejo de cumplimiento del CTE, pliego de condiciones, mediciones, etc.), USA ESTA HERRAMIENTA.
- Pasa el contenido completo en Markdown en el campo `content`.
- Usa formato "docx" por defecto para documentos técnicos.
- Elige un nombre descriptivo en kebab-case sin extensión (ej: "memoria-descriptiva", "cumplimiento-db-he").
- Después de crear el documento, responde con un breve resumen en el chat. NO repitas el contenido completo.

Archivos adjuntos:
- Si el mensaje comienza con secciones "[Attached: …]", son archivos que el arquitecto ha subido. Trátalos como contexto principal.
- Si hay una imagen adjunta, describe lo que ves y úsala como contexto.

Idioma:
- Responde en el mismo idioma en que escribe el arquitecto."""

        # Volatile tail — recomputed every turn from current user/project
        # state. Rendered as a separate (uncached) system text block so it
        # sits AFTER the ephemeral cache breakpoint and can't byte-
        # invalidate the cached prefix above. Intentionally empty when
        # there's no user profile + no project metadata.
        system_prompt_volatile = ""
        if user_context or project_context:
            system_prompt_volatile = (
                "\n--- Sesión actual ---\n" + user_context + project_context
            )

        tools = [
            {
                "name": "search_normativa",
                "description": (
                    "Busca en la normativa indexada:\n"
                    "  - **PGOU/PGOM municipales** — Málaga, Marbella, "
                    "Torremolinos, Fuengirola, Mijas, Estepona, Nerja, "
                    "Benalmádena, Alhaurín de la Torre, Rincón de la "
                    "Victoria, Vélez-Málaga y Antequera. Cuando el "
                    "proyecto tiene un municipio concreto la búsqueda se "
                    "limita automáticamente a ese municipio; si el "
                    "municipio del proyecto NO está en esa lista, la "
                    "búsqueda de PGOU devuelve cero resultados y debes "
                    "decirlo explícitamente al arquitecto.\n"
                    "  - **CTE** — los seis Documentos Básicos (DB-SE, "
                    "DB-SI, DB-SUA, DB-HS, DB-HR, DB-HE) más sus "
                    "Documentos de Apoyo (DA-DB-xx-N).\n"
                    "  - **LOE** — Ley 38/1999 de Ordenación de la "
                    "Edificación (agentes, licencias, garantías, "
                    "dirección facultativa, seguros decenales, etc.).\n\n"
                    "Devuelve fragmentos con su fuente y página. Usa "
                    "`category` para acotar: 'pgou' sólo urbanismo "
                    "municipal, 'cte' sólo CTE, 'loe' sólo LOE, 'both' "
                    "(por defecto) los tres juntos."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Consulta de búsqueda (puede ser pregunta "
                                "natural o referencia a artículo/sección "
                                "específica, p.ej. 'DB-HE 1 apartado 2' o "
                                "'artículo 6.2.3')."
                            ),
                        },
                        "category": {
                            "type": "string",
                            "enum": ["pgou", "cte", "loe", "both"],
                            "description": (
                                "Corpus a consultar. 'pgou' → plan "
                                "urbanístico del municipio del proyecto "
                                "(si está cubierto). 'cte' → CTE + DAs. "
                                "'loe' → Ley de Ordenación de la "
                                "Edificación (Ley 38/1999). 'both' (por "
                                "defecto) → PGOU + CTE + LOE juntos."
                            ),
                            "default": "both",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Número de resultados (default 8)",
                            "default": 8,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "create_document",
                "description": (
                    "Create a downloadable document for the student. Call this "
                    "whenever the student asks you to write, draft, export, or "
                    "generate a document they'll want to save or hand in."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": (
                                "Short descriptive filename in kebab-case, "
                                "without extension (e.g. 'essay-feedback')."
                            ),
                        },
                        "format": {
                            "type": "string",
                            "enum": ["docx", "md"],
                            "description": "File format. Default docx.",
                            "default": "docx",
                        },
                        "content": {
                            "type": "string",
                            "description": (
                                "Full document content in Markdown. Supports "
                                "headings, lists, bold, italic, inline code."
                            ),
                        },
                        "title": {
                            "type": "string",
                            "description": (
                                "Optional document title to render at the top."
                            ),
                        },
                    },
                    "required": ["filename", "content"],
                },
            },
            {
                "name": "consultar_catastro",
                "description": (
                    "Consulta los servicios INSPIRE WFS del Catastro español "
                    "(wfsCP para parcela + wfsBU para edificio) para obtener "
                    "datos de un inmueble a partir de su referencia catastral. "
                    "Devuelve la superficie gráfica del solar, la superficie "
                    "construida total, el uso actual, año de construcción, "
                    "número de plantas, número de unidades y viviendas, "
                    "estado de construcción y dirección normalizada. "
                    "Usa esta herramienta cuando necesites verificar o "
                    "consultar datos catastrales de una referencia."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ref_catastral": {
                            "type": "string",
                            "description": (
                                "Referencia catastral de 14 o 20 caracteres. "
                                "Ejemplo: '8937004TP8293N'"
                            ),
                        },
                    },
                    "required": ["ref_catastral"],
                },
            },
            {
                "name": "consultar_bcca",
                "description": (
                    "Consulta el Banco de Coste de la Construcción de "
                    "Andalucía (BCCA) — la base de precios POR DEFECTO para "
                    "tablas, partidas, mediciones y presupuestos. Devuelve "
                    "filas con código, descripción, unidad y precio en EUR. "
                    "Úsala SIEMPRE que el arquitecto pida precios, estimaciones "
                    "de PEM/PEC o tablas de partidas, a menos que pida "
                    "explícitamente otra base de precios. Puedes buscar por "
                    "palabras clave de la descripción (parámetro `query`) o "
                    "por código (parámetro `codigo`, exacto o por prefijo)."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Palabras clave sobre la descripción del "
                                "elemento. Ejemplos: 'arena cernida', "
                                "'hormigón HA-25', 'oficial 1ª albañilería', "
                                "'tabique ladrillo hueco doble'."
                            ),
                        },
                        "codigo": {
                            "type": "string",
                            "description": (
                                "Código BCCA exacto o prefijo. Ejemplo: "
                                "'AA00100' (exacto) o 'AA001' (prefijo)."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Máximo de resultados (default 25).",
                            "default": 25,
                        },
                    },
                },
            },
        ]

        all_sources = []
        generated_documents: List[Dict[str, Any]] = []
        # Track which tools actually executed during this turn so the frontend
        # can light up the matching source indicator. Order preserved,
        # duplicates allowed (a tool called twice counts once thanks to the
        # `in` check below).
        tools_used: List[str] = []
        # Pull the municipio once so every search_normativa call this turn
        # filters PGOU chunks to the project's municipality.
        project_municipio: Optional[str] = None
        if project_metadata:
            mv = project_metadata.get("municipio")
            if isinstance(mv, str) and mv.strip():
                project_municipio = mv.strip()

        # ── Prompt caching setup ────────────────────────────────
        # We insert two `cache_control: ephemeral` breakpoints:
        #
        #   1. end of the system prompt  — stays hot across ALL requests
        #      (same system text for every user / conversation), so every
        #      follow-up turn gets a cache hit on the ~1 kB system block.
        #
        #   2. end of the last message BEFORE the current user turn —
        #      caches the full conversation prefix including any
        #      attachments. On turn N+1, the identical prefix matches and
        #      the re-sent PDF text / image blocks cost ~10% of full.
        #
        # Anthropic has a minimum cacheable-block size (1024 tokens for
        # Sonnet). If we're under it, the breakpoint is silently a no-op
        # and we just pay normal price — no error, no broken behaviour.
        # Two-block system prompt: the stable block carries the cache
        # breakpoint, the volatile block (user + project context) sits
        # after it so its byte-churn never invalidates the cached prefix.
        # When the volatile block is empty (no profile, no project), we
        # omit it entirely — Anthropic rejects empty text blocks.
        system_param: List[Dict[str, Any]] = [
            {
                "type": "text",
                "text": system_prompt_stable,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        if system_prompt_volatile.strip():
            system_param.append({
                "type": "text",
                "text": system_prompt_volatile,
            })

        # Apply the second breakpoint in-place on `messages[-2]` (the
        # last history entry — messages[-1] is the fresh current turn).
        #
        # IMPORTANT: cache_control cannot sit on an empty text block,
        # because Anthropic rejects that with
        # `cache_control cannot be set for empty text blocks`. This
        # happens in practice when Claude's previous turn only emitted
        # a tool_use with no preamble text. We defensively walk backwards
        # through the target message's blocks and attach the marker to
        # the first block that's actually eligible (non-empty text, or
        # any non-text block like tool_use / image). If nothing in the
        # target message is eligible, we skip the breakpoint silently.
        def _attach_cache_marker(blocks: List[Dict[str, Any]]) -> bool:
            for i in range(len(blocks) - 1, -1, -1):
                blk = blocks[i]
                btype = blk.get("type")
                if btype == "text":
                    if not (blk.get("text") or "").strip():
                        continue  # empty text block — not eligible
                # Either non-empty text, or a non-text block — ok.
                blocks[i] = {**blk, "cache_control": {"type": "ephemeral"}}
                return True
            return False

        if len(messages) >= 2:
            last_hist_idx = len(messages) - 2
            last_hist = messages[last_hist_idx]
            content = last_hist["content"]

            if isinstance(content, str):
                if content.strip():
                    patched_content: List[Dict[str, Any]] = [
                        {
                            "type": "text",
                            "text": content,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ]
                    messages[last_hist_idx] = {
                        "role": last_hist["role"],
                        "content": patched_content,
                    }
                # else: empty string history entry — skip marker
            else:
                # Already a list of blocks — copy (avoid mutating shared
                # refs from the caller) and attach the marker.
                patched_content = [dict(b) for b in content]
                if _attach_cache_marker(patched_content):
                    messages[last_hist_idx] = {
                        "role": last_hist["role"],
                        "content": patched_content,
                    }
                # else: nothing eligible in this message — skip marker

        # Stream the initial response so text deltas flow to the caller
        # in real time. We still need the full final message afterwards
        # so we can detect `tool_use` stops and keep the loop going.
        async with self.anthropic_client.beta.messages.stream(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4000,
            system=system_param,
            tools=tools,
            messages=messages,
            betas=["files-api-2025-04-14"],
        ) as stream:
            async for event in stream:
                if getattr(event, "type", "") == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if delta and getattr(delta, "type", "") == "text_delta":
                        text_chunk = getattr(delta, "text", "") or ""
                        if text_chunk:
                            yield {"type": "text_delta", "text": text_chunk}
            response = await stream.get_final_message()
        self._log_cache_usage("initial", response)

        # Handle tool calls
        while response.stop_reason == "tool_use":
            # Handle ALL tool_use blocks in this response (Claude can call
            # multiple tools in one turn, e.g. search_normativa + consultar_catastro).
            # Each tool_use MUST have a corresponding tool_result or the API rejects it.
            tool_uses = [block for block in response.content if block.type == "tool_use"]
            tool_results: List[Dict[str, Any]] = []

            for tool_use in tool_uses:
                tool_input = tool_use.input

                # Emit a lightweight event so the UI can light the matching
                # indicator the moment a tool starts, even before it
                # finishes. The chat-page source-indicator row already
                # knows how to reflect this from the `tools_used` state
                # updated below — this event is just the "live" nudge.
                yield {"type": "tool_call", "name": tool_use.name}

                if tool_use.name == "search_normativa":
                    # Track which normativa corpus got hit so the UI can light
                    # the matching indicator (pgou, cte, or both).
                    cat = (tool_input.get("category") or "both").lower()
                    if cat in ("pgou", "both") and "pgou" not in tools_used:
                        tools_used.append("pgou")
                    if cat in ("cte", "both") and "cte" not in tools_used:
                        tools_used.append("cte")

                    search_results = await self._search_documents(
                        query=tool_input["query"],
                        subject=subject_filter,
                        level=level_filter,
                        max_results=tool_input.get("max_results", 8),
                        category=tool_input.get("category"),
                        project_municipio=project_municipio,
                    )
                    all_sources.extend(search_results)

                    if search_results:
                        result_text = "Documentos normativos encontrados:\n\n"
                        for i, doc in enumerate(search_results, 1):
                            page = doc.get("page_number")
                            page_str = f" (p.{page})" if page else ""
                            section = doc.get("subject") or ""
                            result_text += f"[Fuente {i}: {doc['source']} — {section}{page_str}]\n"
                            result_text += f"{doc['content']}\n\n"
                    else:
                        result_text = "No se encontraron documentos relevantes."

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result_text,
                    })
                elif tool_use.name == "create_document":
                    fmt = (tool_input.get("format") or "docx").lower()
                    base = (tool_input.get("filename") or "document").strip() or "document"
                    content = tool_input.get("content") or ""
                    title = tool_input.get("title")

                    if fmt == "md":
                        data = markdown_to_bytes(content)
                        mime_type = "text/markdown"
                        filename = f"{base}.md"
                    else:
                        data = markdown_to_docx_bytes(content, title=title)
                        mime_type = (
                            "application/vnd.openxmlformats-officedocument."
                            "wordprocessingml.document"
                        )
                        filename = f"{base}.docx"

                    generated_documents.append(
                        {
                            "filename": filename,
                            "mime_type": mime_type,
                            "data": data,
                            "size_bytes": len(data),
                        }
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": (
                            f"Document '{filename}' created ({len(data)} bytes). "
                            "El arquitecto puede descargarlo desde el chat."
                        ),
                    })
                elif tool_use.name == "consultar_catastro":
                    if "catastro" not in tools_used:
                        tools_used.append("catastro")
                    from app.services.catastro import lookup_by_ref

                    ref_input = tool_input.get("ref_catastral", "") or tool_input.get("address", "")

                    # Short-circuit: if Claude asks for the same ref that the
                    # project already has catastro data for, reuse the cached
                    # result instead of re-running the 4 WFS calls (~2-5s).
                    cached = (project_metadata or {}).get("catastro_data") or {}
                    cached_ref = (cached.get("ref_catastral") or "").strip().upper()
                    requested_ref = (ref_input or "").strip().upper()[:14]
                    if (
                        cached.get("success")
                        and cached_ref == requested_ref
                        and len(cached_ref) == 14
                    ):
                        logger.info(
                            f"consultar_catastro short-circuit hit for {cached_ref} — "
                            f"using project's cached data"
                        )
                        catastro_result = cached
                    else:
                        catastro_result = await lookup_by_ref(ref_input)

                    if catastro_result.get("success"):
                        sup_grafica = catastro_result.get("superficie_grafica") or "No disponible"
                        sup_construida = catastro_result.get("superficie_construida") or "No disponible"
                        sup_tipo = catastro_result.get("superficie_construida_tipo") or "grossFloorArea"
                        num_plantas = catastro_result.get("num_plantas") or "No disponible"
                        num_plantas_bajo = catastro_result.get("num_plantas_bajo_rasante") or "0"
                        num_unidades = catastro_result.get("num_unidades") or "No disponible"
                        num_viviendas = catastro_result.get("num_viviendas") or "No disponible"
                        num_edificios = catastro_result.get("num_edificios")
                        num_edificios_str = str(num_edificios) if num_edificios is not None else "1"

                        result_text = (
                            f"Datos obtenidos de los servicios INSPIRE WFS del Catastro (CP + BU):\n\n"
                            f"DATOS DESCRIPTIVOS DEL INMUEBLE:\n"
                            f"- Referencia catastral: {catastro_result.get('ref_catastral', 'N/A')}\n"
                            f"- Localización: {catastro_result.get('direccion_normalizada', 'N/A')}\n"
                            f"- Código postal: {catastro_result.get('codigo_postal', 'N/A')}\n"
                            f"- Provincia: {catastro_result.get('provincia', 'N/A')}\n"
                            f"- Municipio: {catastro_result.get('municipio', 'N/A')}\n"
                            f"\nPARCELA CATASTRAL (WFS CP):\n"
                            f"- Superficie gráfica del solar: {sup_grafica} m²\n"
                            f"\nEDIFICIO (WFS BU):\n"
                            f"- Uso actual: {catastro_result.get('uso', 'N/A')} "
                            f"(código INSPIRE: {catastro_result.get('uso_codigo', 'N/A')})\n"
                            f"- Año de construcción: {catastro_result.get('anio_construccion', 'N/A')}\n"
                            f"- Superficie construida total: {sup_construida} m² ({sup_tipo})\n"
                            f"- Número de plantas sobre rasante: {num_plantas}\n"
                            f"- Número de plantas bajo rasante: {num_plantas_bajo}\n"
                            f"- Número de unidades del edificio: {num_unidades}\n"
                            f"- Número de viviendas: {num_viviendas}\n"
                            f"- Estado de la construcción: {catastro_result.get('estado_construccion', 'N/A')}\n"
                            f"- Edificios en la parcela: {num_edificios_str}\n"
                            f"\nURL Sede Electrónica: {catastro_result.get('sede_url', 'N/A')}\n"
                        )

                        # Append any partial failures (one of the two WFS calls failed)
                        warnings = catastro_result.get("warnings") or {}
                        if warnings.get("parcel_error"):
                            result_text += f"\n⚠️ No se pudo obtener datos de parcela: {warnings['parcel_error']}\n"
                        if warnings.get("building_error"):
                            result_text += f"\n⚠️ No se pudo obtener datos de edificio: {warnings['building_error']}\n"
                    else:
                        result_text = f"Error al consultar el Catastro: {catastro_result.get('error', 'desconocido')}"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result_text,
                    })
                elif tool_use.name == "consultar_bcca":
                    if "bcca" not in tools_used:
                        tools_used.append("bcca")
                    from app.services.bcca import buscar_bcca, format_results_for_llm

                    bcca_result = buscar_bcca(
                        self.supabase,
                        query=tool_input.get("query"),
                        codigo=tool_input.get("codigo"),
                        limit=tool_input.get("limit") or 25,
                    )
                    result_text = format_results_for_llm(bcca_result)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result_text,
                    })
                else:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": "Tool not found",
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            async with self.anthropic_client.beta.messages.stream(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4000,
                system=system_param,
                tools=tools,
                messages=messages,
                betas=["files-api-2025-04-14"],
            ) as stream:
                async for event in stream:
                    if getattr(event, "type", "") == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if delta and getattr(delta, "type", "") == "text_delta":
                            text_chunk = getattr(delta, "text", "") or ""
                            if text_chunk:
                                yield {"type": "text_delta", "text": text_chunk}
                response = await stream.get_final_message()
            self._log_cache_usage("tool-loop", response)

        # Extract final text
        final_response = ""
        for block in response.content:
            if hasattr(block, "text"):
                final_response += block.text

        # Deduplicate sources
        unique_sources = []
        seen = set()
        for source in all_sources:
            key = source["source"]
            if key not in seen:
                seen.add(key)
                unique_sources.append(source)

        yield {
            "type": "final",
            "response": final_response,
            "sources": unique_sources,
            "documents": generated_documents,
            "tools_used": tools_used,
        }

    async def chat(
        self,
        message: Union[str, List[Dict[str, Any]]],
        conversation_history: List[Dict[str, str]] = None,
        user_profile: Optional[Dict] = None,
        project_metadata: Optional[Dict] = None,
        subject_filter: Optional[str] = None,
        level_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Non-streaming wrapper around `chat_stream` — collects every event
        and returns the same dict shape the old synchronous chat used to
        produce. Callers that want progressive token rendering should use
        `chat_stream` directly; this one exists for the legacy JSON
        endpoint and for background jobs that don't care about deltas.
        """
        final: Optional[Dict[str, Any]] = None
        async for event in self.chat_stream(
            message=message,
            conversation_history=conversation_history,
            user_profile=user_profile,
            project_metadata=project_metadata,
            subject_filter=subject_filter,
            level_filter=level_filter,
        ):
            if event.get("type") == "final":
                final = event
        if final is None:
            # chat_stream always yields a final event at the end; if we
            # got here, something is seriously wrong (SDK crash, etc.).
            return {
                "response": "",
                "sources": [],
                "documents": [],
                "tools_used": [],
            }
        return {
            "response": final["response"],
            "sources": final["sources"],
            "documents": final["documents"],
            "tools_used": final["tools_used"],
        }

    async def generate_title(self, user_message: str, assistant_response: str) -> str:
        """
        Generate a short, descriptive title for a conversation based on the
        first exchange. Uses Haiku for speed + cost. Returns a fallback
        derived from the user message if the call fails.
        """
        try:
            resp = await self.anthropic_client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=40,
                system=(
                    "Genera títulos muy cortos (3 a 6 palabras, sin comillas, "
                    "sin puntuación final, sin emojis) que resuman el TEMA "
                    "de una consulta de arquitectura. Responde solo con el texto del título."
                ),
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"User: {user_message}\n"
                            f"Assistant: {assistant_response[:500]}\n\n"
                            "Title:"
                        ),
                    }
                ],
            )
            title = ""
            for block in resp.content:
                if hasattr(block, "text"):
                    title += block.text
            title = title.strip().strip('"').strip("'").rstrip(".").strip()
            if not title:
                raise ValueError("empty title from model")
            return title[:80]
        except Exception as e:
            logger.warning(f"Title generation failed, using fallback: {e}")
            return (user_message[:50] + ("..." if len(user_message) > 50 else "")) or "New conversation"
