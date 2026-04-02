"""
goochland.py — Goochland County permit scraper.

Portal: EnerGov Self-Service (Tyler Technologies)
URL: https://goochlandcountyva-energovweb.tylerhost.net/apps/selfservice

STATUS: BLOCKED — EnerGov portal requires Tyler Identity SSO login for permit
search. No public search, no open data API. Only 2 target ZIPs (23103, 23129).

Options:
  - Manual FOIA/records request to Building Inspection: 804-556-5860
  - Monitor for portal changes (Tyler EnerGov sometimes adds public search later)

ZIPs: 23103, 23129
"""
import logging

log = logging.getLogger(__name__)


def fetch_permits(since_days: int = 14) -> list[dict]:
    """Goochland EnerGov portal requires login — cannot scrape publicly."""
    log.info("Goochland: skipped — EnerGov portal requires login (no public permit search)")
    return []
