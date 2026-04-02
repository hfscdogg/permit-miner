"""
assessor.py — Property assessed value lookup via county ArcGIS REST services.

Supported counties:
  - Chesterfield: ArcGIS Cadastral_ProdA FeatureServer → TotalAssessment
  - Hanover: ArcGIS Hanover_Parcels FeatureServer → LAND_VALUE + IMPROVEMENTS_VALUE
  - Henrico: values come from Excel import (no public ArcGIS service)
  - Powhatan: values come from PDF permit logs

Returns assessed value in dollars (not cents — callers convert as needed).
"""
import logging
import re

import httpx

log = logging.getLogger(__name__)

# Chesterfield County — Cadastral_ProdA FeatureServer layer 3 (ParcelsEnriched)
CHESTERFIELD_URL = (
    "https://services3.arcgis.com/TsynfzBSE6sXfoLq/arcgis/rest/services/"
    "Cadastral_ProdA/FeatureServer/3/query"
)

# Hanover County — Hanover_Parcels FeatureServer layer 0
HANOVER_URL = (
    "https://services2.arcgis.com/sKZWgJlU6SekCzQV/arcgis/rest/services/"
    "Hanover_Parcels/FeatureServer/0/query"
)

# ZIP → county mapping
CHESTERFIELD_ZIPS = {"23113", "23114", "23146", "23838"}
HANOVER_ZIPS = {"23005", "23116"}


def get_assessed_value(address: str, zip_code: str) -> int:
    """
    Look up assessed property value in dollars.
    Returns 0 if lookup fails or address not found.
    """
    zip_code = (zip_code or "").strip()[:5]

    if zip_code in CHESTERFIELD_ZIPS:
        return _chesterfield_lookup(address, zip_code)

    if zip_code in HANOVER_ZIPS:
        return _hanover_lookup(address)

    return 0


def _chesterfield_lookup(address: str, zip_code: str) -> int:
    """
    Query Chesterfield ArcGIS by street address.
    Field: TotalAssessment (land + improvements, dollars).
    """
    street = _normalize_street(address)
    if not street:
        return 0

    params = {
        "where": f"Address LIKE '{_esc(street)}%' AND Zip LIKE '{_esc(zip_code)}%'",
        "outFields": "Address,TotalAssessment,OwnerName",
        "f": "json",
        "returnGeometry": "false",
        "resultRecordCount": 5,
    }

    try:
        r = httpx.get(CHESTERFIELD_URL, params=params, timeout=15)
        if r.status_code != 200:
            log.debug("Chesterfield ArcGIS returned %d for '%s'", r.status_code, street)
            return 0

        features = r.json().get("features") or []
        if not features:
            # Retry without ZIP (some addresses have ZIP mismatches)
            params["where"] = f"Address LIKE '{_esc(street)}%'"
            r = httpx.get(CHESTERFIELD_URL, params=params, timeout=15)
            features = r.json().get("features") or [] if r.status_code == 200 else []

        if features:
            attrs = features[0].get("attributes") or {}
            total = attrs.get("TotalAssessment") or 0
            log.debug("Chesterfield: %s → $%s (owner: %s)",
                      street, f"{total:,}", attrs.get("OwnerName", ""))
            return int(total)

    except Exception as e:
        log.debug("Chesterfield ArcGIS lookup failed for '%s': %s", street, e)

    return 0


def _hanover_lookup(address: str) -> int:
    """
    Query Hanover ArcGIS by house number + street name.
    Fields: LAND_VALUE + IMPROVEMENTS_VALUE (dollars).
    Hanover stores address components separately: ADDRESS (number), ST_NAME, ST_TYPE.
    """
    house_num, street_name = _split_house_street(address)
    if not house_num:
        return 0

    # Build WHERE clause
    where = f"ADDRESS = '{_esc(house_num)}'"
    if street_name:
        where += f" AND ST_NAME LIKE '%{_esc(street_name)}%'"

    params = {
        "where": where,
        "outFields": "ADDRESS,ST_NAME,ST_TYPE,OWN_NAME1,LAND_VALUE,IMPROVEMENTS_VALUE",
        "f": "json",
        "returnGeometry": "false",
        "resultRecordCount": 5,
    }

    try:
        r = httpx.get(HANOVER_URL, params=params, timeout=15)
        if r.status_code != 200:
            log.debug("Hanover ArcGIS returned %d for '%s %s'", r.status_code, house_num, street_name)
            return 0

        features = r.json().get("features") or []
        if features:
            attrs = features[0].get("attributes") or {}
            land = attrs.get("LAND_VALUE") or 0
            improvements = attrs.get("IMPROVEMENTS_VALUE") or 0
            total = int(land + improvements)
            log.debug("Hanover: %s %s → $%s (owner: %s)",
                      house_num, street_name, f"{total:,}", attrs.get("OWN_NAME1", ""))
            return total

    except Exception as e:
        log.debug("Hanover ArcGIS lookup failed for '%s': %s", address, e)

    return 0


def enrich_permits(permits: list[dict]) -> list[dict]:
    """
    Batch-enrich a list of permit dicts with assessed values.
    Only queries ArcGIS for permits that don't already have a value.
    Updates each permit's 'assessed_value_dollars' in place.
    """
    enriched = 0
    for p in permits:
        existing = p.get("assessed_value_dollars") or p.get("job_value_dollars") or 0
        if existing > 0:
            continue

        value = get_assessed_value(
            p.get("property_address", ""),
            p.get("property_zip", ""),
        )
        if value > 0:
            p["assessed_value_dollars"] = value
            enriched += 1

    log.info("Assessor enrichment: %d of %d permits got values", enriched, len(permits))
    return permits


# ── Helpers ──────────────────────────────────────────────────────────────────

def _normalize_street(address: str) -> str:
    """Extract street address (before comma or ZIP), uppercase."""
    if not address:
        return ""
    street = address.split(",")[0].strip()
    # Remove unit/apt suffixes
    street = re.sub(r"\s+(APT|UNIT|STE|SUITE|#)\s*\S*$", "", street, flags=re.IGNORECASE)
    return street.upper()


def _split_house_street(address: str) -> tuple[str, str]:
    """
    Split '801 S Center ST' into house number ('801') and street name ('Center').
    Hanover ArcGIS stores: ADDRESS='801', ST_NAME='Center'.
    """
    street = _normalize_street(address)
    if not street:
        return "", ""

    m = re.match(r"^(\d+)\s+(.+)", street)
    if not m:
        return "", ""

    house_num = m.group(1)
    remainder = m.group(2)

    # Remove directional prefix (N, S, E, W) and street type suffix (ST, RD, DR, etc.)
    remainder = re.sub(r"^(N|S|E|W|NE|NW|SE|SW)\s+", "", remainder, flags=re.IGNORECASE)
    remainder = re.sub(
        r"\s+(ST|RD|DR|CT|LN|WAY|BLVD|AVE|PL|TER|CIR|TRL|PKWY|HWY|LOOP)\s*$",
        "", remainder, flags=re.IGNORECASE,
    )

    return house_num, remainder.strip()


def _esc(s: str) -> str:
    """Escape single quotes for ArcGIS SQL WHERE clauses."""
    return s.replace("'", "''").replace(";", "").replace("--", "")
