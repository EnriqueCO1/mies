"""
BCCA lookup — Banco de Coste de la Construcción de Andalucía.

Exposes a single `buscar_bcca()` helper that the Claude tool handler uses.
The BCCA table in Supabase has the following columns (confirmed with the user):
    codigo       text     e.g. "AA00100"
    unidad       text     e.g. "m3"
    descripcion  text     e.g. "ARENA CERNIDA"
    precio       numeric  e.g. 12.76

Search strategy:
  1. If `codigo` is supplied → exact match (case insensitive).
  2. Else split `query` into whitespace-separated words and AND-ilike each
     one against `descripcion`. If AND returns nothing, fall back to OR on
     any word to avoid missing partial matches.
  3. Cap results at `limit` (default 25).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging
import re

logger = logging.getLogger(__name__)

# Keep words that carry signal — drop connectors that are too generic.
_STOPWORDS = {
    "de", "del", "la", "las", "el", "los", "y", "o", "a", "en", "con",
    "para", "por", "un", "una", "unos", "unas", "al", "lo",
}


def _tokenize(query: str) -> List[str]:
    """Normalise query into meaningful keywords."""
    if not query:
        return []
    # Split on whitespace + strip punctuation. Keep alphanumerics and accents.
    raw = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9/]+", query)
    return [w for w in raw if len(w) >= 2 and w.lower() not in _STOPWORDS]


def buscar_bcca(
    client,
    *,
    query: Optional[str] = None,
    codigo: Optional[str] = None,
    limit: int = 25,
) -> Dict[str, Any]:
    """
    Search the BCCA table.

    Returns a dict with:
        success:  bool
        count:    int
        items:    List[{codigo, unidad, descripcion, precio}]
        mode:     str — 'codigo' | 'and' | 'or' | 'empty'
        error:    Optional[str]
    """
    table_reachable: Optional[bool] = None

    def _ret(**kwargs) -> Dict[str, Any]:
        # Inject the reachability flag so format_results_for_llm can tell
        # "no matches" apart from "table empty / RLS blocked".
        kwargs.setdefault("table_reachable", table_reachable)
        return kwargs

    try:
        # Cheap reachability probe: count rows the caller can actually see.
        # If 0, the table is either empty or an RLS policy is hiding rows.
        try:
            probe = (
                client.table("BCCA")
                .select("codigo", count="exact")
                .limit(1)
                .execute()
            )
            table_reachable = bool(probe.count and probe.count > 0)
        except Exception:
            table_reachable = None  # unknown — treat as normal lookup

        if codigo:
            code = codigo.strip()
            # Exact match first
            exact = (
                client.table("BCCA")
                .select("codigo,unidad,descripcion,precio_eur")
                .ilike("codigo", code)
                .limit(limit)
                .execute()
                .data
                or []
            )
            if exact:
                return _ret(
                    success=True,
                    mode="codigo",
                    count=len(exact),
                    items=exact,
                    error=None,
                )
            # Prefix match ("AA001" → "AA001%") as a fallback
            prefix_results = (
                client.table("BCCA")
                .select("codigo,unidad,descripcion,precio_eur")
                .ilike("codigo", f"{code}%")
                .order("codigo")
                .limit(limit)
                .execute()
                .data
                or []
            )
            return _ret(
                success=True,
                mode="codigo",
                count=len(prefix_results),
                items=prefix_results,
                error=None,
            )

        words = _tokenize(query or "")
        if not words:
            return _ret(
                success=False,
                mode="empty",
                count=0,
                items=[],
                error="Proporciona un `query` o un `codigo` para buscar.",
            )

        # AND match — every word must appear in descripcion
        q = client.table("BCCA").select("codigo,unidad,descripcion,precio_eur")
        for w in words:
            # Escape PostgREST-reserved chars in the value
            safe = w.replace("%", r"\%").replace(",", r"\,")
            q = q.ilike("descripcion", f"%{safe}%")
        and_rows = q.limit(limit).execute().data or []
        if and_rows:
            return _ret(
                success=True,
                mode="and",
                count=len(and_rows),
                items=and_rows,
                error=None,
            )

        # Fallback: OR match on any single word
        or_terms = ",".join(
            f"descripcion.ilike.%{w.replace('%', chr(92) + '%').replace(',', chr(92) + ',')}%"
            for w in words
        )
        or_rows = (
            client.table("BCCA")
            .select("codigo,unidad,descripcion,precio_eur")
            .or_(or_terms)
            .limit(limit)
            .execute()
            .data
            or []
        )
        return _ret(
            success=True,
            mode="or",
            count=len(or_rows),
            items=or_rows,
            error=None,
        )

    except Exception as e:
        logger.error(f"BCCA lookup failed: {e}")
        return {
            "success": False,
            "mode": "error",
            "count": 0,
            "items": [],
            "table_reachable": table_reachable,
            "error": str(e),
        }


def format_results_for_llm(result: Dict[str, Any]) -> str:
    """Turn a buscar_bcca() result into a compact tool_result text block."""
    if not result.get("success"):
        return (
            f"No se pudo consultar la BCCA: {result.get('error', 'error desconocido')}"
        )
    items = result.get("items") or []
    if not items:
        # Distinguish "table is empty / RLS blocks reads" from "no matches for
        # this specific query" so Claude can tell the architect the right thing.
        if result.get("table_reachable") is False:
            return (
                "No puedo acceder ahora mismo a la tabla del Banco de Coste de "
                "la Construcción de Andalucía (BCCA). La tabla está vacía o el "
                "administrador debe añadir una política RLS de lectura para el "
                "rol `authenticated`. Indícaselo al arquitecto en lugar de "
                "inventar precios."
            )
        return (
            "Sin coincidencias en el Banco de Coste de la Construcción de "
            "Andalucía (BCCA) para esta consulta."
        )

    header = (
        f"Banco de Coste de la Construcción de Andalucía (BCCA) — "
        f"{result['count']} coincidencias (modo: {result['mode']}):\n\n"
    )
    # Tabular layout for Claude — consistent columns, easy to reformat.
    lines = [
        "| Código | Descripción | Unidad | Precio (EUR) |",
        "|--------|-------------|--------|--------------|",
    ]
    for it in items:
        precio = it.get("precio_eur")
        try:
            precio_str = f"{float(precio):.2f}" if precio is not None else "—"
        except (TypeError, ValueError):
            precio_str = str(precio) if precio is not None else "—"
        # Keep the description on one row for a clean table. Escape pipes.
        desc = (it.get("descripcion") or "").replace("|", "/")
        lines.append(
            f"| {it.get('codigo') or ''} "
            f"| {desc} "
            f"| {it.get('unidad') or ''} "
            f"| {precio_str} |"
        )
    return header + "\n".join(lines)
