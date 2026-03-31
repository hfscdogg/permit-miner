"""
assessor.py — Property assessed value lookup via ArcGIS parcel REST services.

Primary: Chesterfield County ArcGIS (opengeospace.com)
Fallback: job_value threshold (>= $75K) or new construction keyword

Returns assessed value in dollars (not cents — callers convert as needed).
"""
import logging

import httpx

log = logging.getLogger(__name__)

# Chesterfield County ArcGIS parcel layer
# Source: https://opengeospace.com/chesterfield-va/
CHESTERFIELD_ARCGIS = (
    "https://services1.arcgis.com/XnVDrSPHdUJqEnGr/arcgis/rest/services/"
    "ParcelData/FeatureServer/0/query"
)

# Henrico County ArcGIS (GIS portal)
HENRICO_ARCGIS = (
    "https://gis.henrico.us/arcgis/rest/services/Parcel/MapServer/0/query"
)


def get_assessed_value(address: str, zip_code: str) -> int:
    """
    Look up assessed property value in dollars.
    Returns 0 if lookup fails or address not found.
    """
    zip_code = zip_code.strip()

    if zip_code in {"23113", "23114", "23146", "23838"}:
        return _chesterfield_lookup(address)

    if zip_code in {"23059", "23060", "23229", "23233", "23238"}:
        return _henrico_lookup(address)

    # Other counties: no ArcGIS endpoint configured yet
    return 0


def _chesterfield_lookup(address: str) -> int:
    """Query Chesterfield ArcGIS parcel service by street address."""
    try:
        # Strip unit numbers and normalize
        street = address.split(",")[0].strip()
        params = {
            "where": f"UPPER(SITE_ADDRESS) LIKE UPPER('{_escape_sql(street)}%')",
            "outFields": "SITE_ADDRESS,TOTAL_VALUE,LAND_VALUE,BLDG_VALUE",
            "f": "json",
            "returnGeometry": "false",
            "resultRecordCount": 5,
        }
        r = httpx.get(CHESTERFIELD_ARCGIS, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            features = data.get("features") or []
            if features:
                attrs = features[0].get("attributes") or {}
                total = attrs.get("TOTAL_VALUE") or attrs.get("BLDG_VALUE") or 0
                return int(total)
    except Exception as e:
        log.debug("Chesterfield ArcGIS lookup failed for '%s': %s", address, e)
    return 0


def _henrico_lookup(address: str) -> int:
    """Query Henrico County ArcGIS parcel service by street address."""
    try:
        street = address.split(",")[0].strip()
        params = {
            "where": f"UPPER(ADDRESS) LIKE UPPER('{_escape_sql(street)}%')",
            "outFields": "ADDRESS,ASSESSED_VALUE,TOTAL_ASSESSED",
            "f": "json",
            "returnGeometry": "false",
            "resultRecordCount": 5,
        }
        r = httpx.get(HENRICO_ARCGIS, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            features = data.get("features") or []
            if features:
                attrs = features[0].get("attributes") or {}
                total = attrs.get("ASSESSED_VALUE") or attrs.get("TOTAL_ASSESSED") or 0
                return int(total)
    except Exception as e:
        log.debug("Henrico ArcGIS lookup failed for '%s': %s", address, e)
    return 0


def _escape_sql(s: str) -> str:
    """Basic SQL injection prevention for ArcGIS WHERE clauses."""
    return s.replace("'", "''").replace(";", "").replace("--", "")
