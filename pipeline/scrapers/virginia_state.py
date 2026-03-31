"""
virginia_state.py — Virginia statewide building permit CSV scraper (STUB).

RESEARCH FINDINGS (March 2026):
- data.virginia.gov does NOT have a statewide building permits CSV.
  The site hosts city-specific datasets (Virginia Beach, Lynchburg, Norfolk, etc.)
  but nothing covering the Richmond metro counties.
- permits.virginia.gov is the Virginia Permit Transparency portal but covers
  only STATE AGENCY permits (VDOT, DCR, DEQ, etc.) — not local building permits.
- Richmond metro county permit data must come from county portals:
    Henrico    → henrico.us Excel download    (pipeline/henrico_import.py)
    Chesterfield → Accela ACA portal          (pipeline/scrapers/chesterfield.py)
    Goochland  → EnerGov portal               (pipeline/scrapers/goochland.py)
    Powhatan   → TBD (stub)                   (pipeline/scrapers/powhatan.py)
    Hanover    → TBD (stub)                   (pipeline/scrapers/hanover.py)

This module is a stub. Returns [] so monday_pull.py logs it cleanly.
If a statewide CSV source is identified in the future, implement fetch_permits() here.
"""
import logging

log = logging.getLogger(__name__)


def fetch_permits(since_days: int = 14) -> list[dict]:
    """
    No statewide Virginia building permits CSV source available.
    County-specific scrapers are the data source.
    """
    log.info(
        "virginia_state: no statewide CSV available — using county portal scrapers."
    )
    return []
