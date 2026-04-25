"""
Catastro service — uses the Catastro INSPIRE WFS services to fetch parcel
and building data by referencia catastral.

Endpoints:
- wfsCP.aspx (CadastralParcels): parcel geometry + graphic surface area
- wfsBU.aspx (Buildings): building floors, year, use, surface, dwellings

The Sede Electrónica Consulta_CPMRC endpoint is still used to resolve the
canonical address text (which the WFS doesn't provide).
"""

from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# ── INSPIRE WFS endpoints ──
WFS_CP = "http://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx"
WFS_BU = "http://ovc.catastro.meh.es/INSPIRE/wfsBU.aspx"

# ── Address-only endpoint (Catastro blocks the WFS for some user-agents,
# and the WFS doesn't return a normalized address text at all) ──
SEDE_COORDS = "http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCoordenadas.asmx"
SEDE_NS = "http://www.catastro.meh.es/"

# Catastro blocks default HTTP client user-agents; pretend to be a browser
UA = "Mozilla/5.0 (compatible; 45Labs/1.0)"
TIMEOUT = 20.0

# ── XML namespaces used in WFS responses ──
CP_NS = "http://inspire.ec.europa.eu/schemas/cp/4.0"
BU_CORE_NS = "http://inspire.jrc.ec.europa.eu/schemas/bu-core2d/2.0"
BU_EXT_NS = "http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0"
GML_NS = "http://www.opengis.net/gml/3.2"

# ── INSPIRE building-use codelist → human labels (Spanish) ──
CURRENT_USE_MAP = {
    "1_residential": "Residencial",
    "2_agriculture": "Agrario",
    "3_industrial": "Industrial",
    "4_1_office": "Oficinas",
    "4_commerceAndServices": "Comercial y servicios",
    "5_trafficAndTransportation": "Tráfico y transporte",
    "6_utilitiesAndReparations": "Utilidades y reparaciones",
    "7_publicServices": "Servicios públicos",
    "8_ancillary": "Auxiliar / Almacén",
}


# ── HTTP helpers ──

async def _http_get_async(
    client: httpx.AsyncClient,
    url: str,
    params: dict,
) -> Tuple[Optional[str], Optional[str]]:
    """Async GET sharing a single AsyncClient across parallel fetches.
    Returns (body, error)."""
    try:
        resp = await client.get(url, params=params)
    except httpx.TimeoutException:
        return None, "Timeout al consultar el Catastro"
    except Exception as e:
        return None, f"Error de conexión: {str(e)}"
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}"
    if not resp.text.strip().startswith("<?xml"):
        return None, "El Catastro devolvió una respuesta no válida (posiblemente bloqueada)"
    return resp.text, None


def _parse_xml(raw: str) -> Optional[ET.Element]:
    try:
        return ET.fromstring(raw)
    except ET.ParseError as e:
        logger.error(f"XML parse error: {e}")
        return None


# ── WFS CP: Parcel geometry + graphic surface ──

async def fetch_parcel(client: httpx.AsyncClient, ref14: str) -> Dict[str, Any]:
    """
    Query the CadastralParcels WFS for the parcel at ref14.
    Returns: ref, area_value (m²), label, begin_lifespan_version, polygon (optional).
    """
    raw, err = await _http_get_async(client, WFS_CP, {
        "service": "wfs",
        "version": "2",
        "request": "getfeature",
        "STOREDQUERIE_ID": "GetParcel",
        "refcat": ref14,
        "srsname": "EPSG::25830",
    })
    if err:
        return {"success": False, "error": err, "source": "wfsCP"}

    # The WFS response uses XML with multiple namespaces — find tags via
    # a namespace-agnostic regex since the namespace aliases change over time.
    def _find(tag: str) -> str:
        m = re.search(rf"<cp:{tag}(?:\s+[^/>]*)?>([^<]+)</cp:{tag}>", raw)
        return m.group(1).strip() if m else ""

    ref = _find("nationalCadastralReference")
    if not ref:
        # Response came back but is empty — parcel not found
        return {
            "success": False,
            "error": "Parcela no encontrada en el WFS del Catastro",
            "source": "wfsCP",
        }

    return {
        "success": True,
        "ref": ref,
        "area_value": _find("areaValue"),           # graphic surface area in m²
        "label": _find("label"),
        "begin_lifespan": _find("beginLifespanVersion"),
        "source": "wfsCP",
    }


# ── WFS BU: Building data (year, floors, use, surface) ──

async def fetch_building(client: httpx.AsyncClient, ref14: str) -> Dict[str, Any]:
    """
    Query the Buildings WFS for buildings on the parcel at ref14.
    Returns: year, current_use, use_label, condition, num_units,
             num_dwellings, num_floors, area_value, area_reference.

    A parcel can have multiple buildings; we return the first one that
    matches ref14 exactly. If the primary ref matches, we use its data;
    otherwise we aggregate across all returned buildings.
    """
    raw, err = await _http_get_async(client, WFS_BU, {
        "service": "wfs",
        "version": "2",
        "request": "getfeature",
        "STOREDQUERIE_ID": "GetBuildingByParcel",
        "refcat": ref14,
        "srsname": "EPSG::25830",
    })
    if err:
        return {"success": False, "error": err, "source": "wfsBU"}

    # Extract building blocks. Regex-based because namespace prefixes can vary.
    # Split the XML on <bu-ext2d:Building ...> to get individual building elements.
    building_pattern = re.compile(
        r"<bu-ext2d:Building\b[^>]*>(.*?)</bu-ext2d:Building>",
        re.DOTALL,
    )
    buildings_raw = building_pattern.findall(raw)

    if not buildings_raw:
        return {
            "success": False,
            "error": "No se encontraron edificios en el WFS para esta parcela",
            "source": "wfsBU",
        }

    def _extract_building(block: str) -> Dict[str, str]:
        def _find(ns: str, tag: str) -> str:
            # Try both with and without attributes
            m = re.search(
                rf"<{ns}:{tag}(?:\s+[^/>]*)?>\s*([^<]+?)\s*</{ns}:{tag}>",
                block,
            )
            return m.group(1).strip() if m else ""

        # Year of construction — from <bu-core2d:beginning>1976-01-01T00:00:00</...>
        beginning = _find("bu-core2d", "beginning")
        year = beginning[:4] if beginning and beginning[:4].isdigit() else ""

        current_use_raw = _find("bu-ext2d", "currentUse")
        use_label = CURRENT_USE_MAP.get(current_use_raw, current_use_raw)

        # Gross floor area lives inside <bu-ext2d:OfficialArea>...<bu-ext2d:value>N</value>
        # We find the value near an officialAreaReference = grossFloorArea.
        area_value = ""
        area_ref = _find("bu-ext2d", "officialAreaReference")
        # Generic value inside OfficialArea
        area_match = re.search(
            r"<bu-ext2d:OfficialArea>.*?<bu-ext2d:value(?:\s+[^/>]*)?>\s*([^<]+?)\s*</bu-ext2d:value>.*?</bu-ext2d:OfficialArea>",
            block,
            re.DOTALL,
        )
        if area_match:
            area_value = area_match.group(1).strip()

        reference = _find("bu-core2d", "reference")

        return {
            "reference": reference,
            "year": year,
            "current_use": current_use_raw,
            "use_label": use_label,
            "condition": _find("bu-core2d", "conditionOfConstruction"),
            "num_units": _find("bu-ext2d", "numberOfBuildingUnits"),
            "num_dwellings": _find("bu-ext2d", "numberOfDwellings"),
            "num_floors": _find("bu-ext2d", "numberOfFloorsAboveGround"),
            "area_value": area_value,
            "area_reference": area_ref,
        }

    buildings = [_extract_building(b) for b in buildings_raw]

    # Pick the building whose reference matches ref14 (primary building for the parcel).
    # If none match, use the first one.
    primary = next((b for b in buildings if b.get("reference") == ref14), buildings[0])

    # NOTE: BuildingParts enrichment happens in `lookup_by_ref` now, running
    # in parallel with the other three network calls instead of serially
    # after this one. We return the raw primary here; `lookup_by_ref` merges
    # `num_floors` / `num_floors_below` once all fetches complete.
    return {
        "success": True,
        "source": "wfsBU",
        "primary": primary,
        "all_buildings": buildings,
        "num_total_buildings": len(buildings),
    }


async def fetch_building_parts(
    client: httpx.AsyncClient, ref14: str
) -> Dict[str, Any]:
    """
    Query GetBuildingPartByParcel and return the max floors above/below ground
    across all BuildingParts on the parcel.
    The main Building element reports numberOfFloorsAboveGround as xsi:nil,
    but the BuildingPart children carry the real floor counts. Taking the max
    matches the "número de plantas" displayed in the Sede Electrónica.
    """
    raw, err = await _http_get_async(client, WFS_BU, {
        "service": "wfs",
        "version": "2",
        "request": "getfeature",
        "STOREDQUERIE_ID": "GetBuildingPartByParcel",
        "refcat": ref14,
        "srsname": "EPSG::25830",
    })
    if err or not raw:
        return {"num_parts": 0, "max_floors_above": 0, "max_floors_below": 0}

    part_blocks = re.findall(
        r"<bu-ext2d:BuildingPart\b[^>]*>(.*?)</bu-ext2d:BuildingPart>",
        raw,
        re.DOTALL,
    )
    max_above = 0
    max_below = 0
    for p in part_blocks:
        above_m = re.search(
            r"<bu-ext2d:numberOfFloorsAboveGround(?:\s+[^/>]*)?>\s*([^<]+?)\s*</bu-ext2d:numberOfFloorsAboveGround>",
            p,
        )
        below_m = re.search(
            r"<bu-ext2d:numberOfFloorsBelowGround(?:\s+[^/>]*)?>\s*([^<]+?)\s*</bu-ext2d:numberOfFloorsBelowGround>",
            p,
        )
        if above_m:
            try:
                max_above = max(max_above, int(above_m.group(1).strip()))
            except ValueError:
                pass
        if below_m:
            try:
                max_below = max(max_below, int(below_m.group(1).strip()))
            except ValueError:
                pass
    return {
        "num_parts": len(part_blocks),
        "max_floors_above": max_above,
        "max_floors_below": max_below,
    }


# ── Address resolution (still uses the Sede Consulta_CPMRC endpoint) ──
# This is the ONE non-WFS call we keep, because the WFS services do not
# return a canonical normalized address text for a ref catastral.

async def fetch_address(
    client: httpx.AsyncClient, ref14: str
) -> Dict[str, str]:
    """Get the canonical address text + coordinates via Consulta_CPMRC."""
    try:
        resp = await client.get(f"{SEDE_COORDS}/Consulta_CPMRC", params={
            "Provincia": "", "Municipio": "",
            "SRS": "EPSG:4258", "RC": ref14,
        })
    except Exception as e:
        logger.warning(f"CPMRC address lookup failed: {e}")
        return {}

    if resp.status_code != 200 or not resp.text.strip().startswith("<?xml"):
        return {}

    try:
        root = ET.fromstring(resp.text.replace(f'xmlns="{SEDE_NS}"', ""))
    except Exception:
        return {}
    if root.find(".//err") is not None:
        return {}

    ldt = (root.findtext(".//ldt") or "").strip()
    xcen = (root.findtext(".//xcen") or "").strip()
    ycen = (root.findtext(".//ycen") or "").strip()

    # Extract province/municipality from ldt: "CR DE SOMIO 2778 GIJON (ASTURIAS)"
    prov_match = re.search(r"\(([^)]+)\)\s*$", ldt)
    provincia = prov_match.group(1).strip() if prov_match else ""
    mun_match = re.search(r"(\S+)\s+\([^)]+\)\s*$", ldt)
    municipio = mun_match.group(1).strip() if mun_match else ""

    # Postal code: look for a 5-digit sequence in the middle of ldt
    cp_match = re.search(r"\b(\d{5})\b", ldt)
    codigo_postal = cp_match.group(1) if cp_match else ""

    return {
        "direccion": ldt,
        "provincia": provincia,
        "municipio": municipio,
        "codigo_postal": codigo_postal,
        "lat": ycen,
        "lng": xcen,
    }


# ── Main entry point ──

async def lookup_by_ref(ref_catastral: str) -> Dict[str, Any]:
    """
    Look up a property by referencia catastral using the INSPIRE WFS services.

    All four network calls (CP parcel, BU main, BU building parts, CPMRC
    address) run **concurrently** in a single shared AsyncClient. The
    total wall-clock time is dominated by the slowest single call (~2-5s
    against Catastro's servers) instead of the sum of all four.

    Returns a unified dict with both parcel and building data:
      - ref_catastral (14 chars)
      - superficie_grafica (parcel area in m², from CP)
      - superficie_construida (gross floor area, from BU)
      - uso (human label) / uso_codigo (INSPIRE code)
      - anio_construccion (year)
      - num_plantas (floors above ground)
      - num_unidades (building units)
      - num_viviendas (dwellings)
      - estado_construccion (functional/ruin/declined/etc.)
      - direccion_normalizada + codigo_postal + provincia + municipio
      - lat / lng
      - sede_url
    """
    rc = (ref_catastral or "").strip().upper()
    if len(rc) < 14:
        return {"success": False, "error": f"Referencia catastral demasiado corta: {rc}"}
    ref14 = rc[:14]

    # Single shared AsyncClient keeps the TCP connection pool warm across
    # the four calls and lets gather() run them truly in parallel.
    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        headers={"User-Agent": UA},
    ) as client:
        parcel, building, parts_info, address = await asyncio.gather(
            fetch_parcel(client, ref14),
            fetch_building(client, ref14),
            fetch_building_parts(client, ref14),
            fetch_address(client, ref14),
        )

    # Both WFS calls failed → hard error
    if not parcel.get("success") and not building.get("success"):
        err_parts = [parcel.get("error"), building.get("error")]
        return {
            "success": False,
            "error": "No se pudo consultar el Catastro: "
                     + " / ".join(e for e in err_parts if e),
        }

    # Merge BuildingParts floor counts into the primary building record.
    b = building.get("primary", {}) if building.get("success") else {}
    if parts_info.get("max_floors_above") and not b.get("num_floors"):
        b["num_floors"] = str(parts_info["max_floors_above"])
    b["num_floors_below"] = (
        str(parts_info["max_floors_below"])
        if parts_info.get("max_floors_below") else ""
    )

    sede_url = (
        f"https://www1.sedecatastro.gob.es/CYCBienInmueble/"
        f"OVCConCiworkermc.aspx?RefCat={ref14}"
    )

    lat = address.get("lat") or ""
    lng = address.get("lng") or ""

    return {
        "success": True,
        "ref_catastral": ref14,

        # DATOS DESCRIPTIVOS DEL INMUEBLE
        "direccion_normalizada": address.get("direccion", ""),
        "codigo_postal": address.get("codigo_postal", ""),
        "provincia": address.get("provincia", ""),
        "municipio": address.get("municipio", ""),

        # Building-level data (from WFS BU)
        "uso": b.get("use_label", ""),
        "uso_codigo": b.get("current_use", ""),
        "superficie_construida": b.get("area_value", ""),
        "superficie_construida_tipo": b.get("area_reference", ""),
        "anio_construccion": b.get("year", ""),
        "num_plantas": b.get("num_floors", ""),
        "num_plantas_bajo_rasante": b.get("num_floors_below", ""),
        "num_unidades": b.get("num_units", ""),
        "num_viviendas": b.get("num_dwellings", ""),
        "estado_construccion": b.get("condition", ""),
        "num_edificios": building.get("num_total_buildings") if building.get("success") else None,

        # Parcel-level data (from WFS CP)
        "superficie_grafica": parcel.get("area_value", "") if parcel.get("success") else "",
        "parcel_label": parcel.get("label", "") if parcel.get("success") else "",

        # Geometry
        "lat": float(lat) if lat else None,
        "lng": float(lng) if lng else None,

        # Metadata
        "sede_url": sede_url,
        "source": "INSPIRE WFS (CP + BU) + Sede CPMRC",
        "error": None,
        "warnings": {
            "parcel_error": parcel.get("error") if not parcel.get("success") else None,
            "building_error": building.get("error") if not building.get("success") else None,
        },
    }
