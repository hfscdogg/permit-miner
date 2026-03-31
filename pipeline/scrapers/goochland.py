"""
goochland.py — Goochland County permit scraper.

Portal: EnerGov Self-Service (Tyler Technologies)
URL: https://land.goochlandva.us/EnerGov_Prod/SelfService

Strategy:
1. Try EnerGov's public JSON search API (used by many Tyler Tech installs).
2. Fall back to Playwright if the JSON endpoints require session cookies.

ZIPs: 23103, 23129
"""
import logging
from datetime import date, timedelta

import httpx

import config

log = logging.getLogger(__name__)

ENERGOV_BASE = "https://land.goochlandva.us/EnerGov_Prod/SelfService"
ENERGOV_API = "https://land.goochlandva.us/EnerGov_Prod/api"
TARGET_ZIPS = config.GOOCHLAND_ZIPS


def fetch_permits(since_days: int = 14) -> list[dict]:
    """Fetch Goochland building permits filed in the last `since_days` days."""
    cutoff = (date.today() - timedelta(days=since_days)).isoformat()
    log.info("Goochland: fetching permits since %s", cutoff)

    results = _try_json_api(cutoff)
    if results is not None:
        log.info("Goochland: %d permits via JSON API", len(results))
        return results

    log.info("Goochland: JSON API unavailable, falling back to Playwright")
    return _try_playwright(cutoff)


def _try_json_api(cutoff: str) -> list[dict] | None:
    """
    EnerGov has a JSON search endpoint used by the SPA frontend.
    POST to /Permits/Search with date filters.
    """
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; PermitMiner/1.0)",
        "Referer": ENERGOV_BASE,
    }

    # EnerGov search payload structure
    payload = {
        "SearchModule": "Permits",
        "FilterModule": "Permits",
        "SearchMainAddress": True,
        "IsMyRecords": False,
        "PageSize": 200,
        "PageNumber": 1,
        "SortBy": "fileDate",
        "SortAscending": False,
        "Filters": [
            {
                "FilterType": "DateRange",
                "FieldName": "fileDate",
                "StartValue": cutoff,
                "EndValue": date.today().isoformat(),
            }
        ],
    }

    try:
        r = httpx.post(
            f"{ENERGOV_API}/Permits/Search",
            json=payload,
            headers=headers,
            timeout=30,
            follow_redirects=True,
        )
        if r.status_code == 200:
            data = r.json()
            records = (
                data.get("Result") or
                data.get("result") or
                data.get("Records") or
                data.get("Permits") or
                []
            )
            if isinstance(records, list):
                normalized = [_normalize_energov_record(rec) for rec in records]
                return [r for r in normalized if r.get("property_zip") in TARGET_ZIPS]
    except Exception as e:
        log.debug("Goochland JSON API attempt failed: %s", e)

    return None


def _try_playwright(cutoff: str) -> list[dict]:
    """Playwright scraper for EnerGov SPA."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("Playwright not installed — run: playwright install chromium")
        return []

    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(f"{ENERGOV_BASE}#/permitsearch", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)

            # EnerGov SPA: look for date filter inputs
            try:
                # File date from
                date_inputs = page.query_selector_all('input[placeholder*="date"], input[type="date"]')
                if date_inputs:
                    date_inputs[0].fill(cutoff)
                    page.click('button[type="submit"], input[type="submit"], button:has-text("Search")')
                    page.wait_for_load_state("networkidle", timeout=20000)
            except Exception as e:
                log.debug("Goochland: could not set date filter: %s", e)

            # Try to extract JSON from network responses via intercepting
            # Alternatively parse the results table
            rows = page.query_selector_all("tr.ng-scope, tr[ng-repeat], .permit-row")
            for row in rows:
                cells = row.query_selector_all("td")
                if len(cells) >= 3:
                    texts = [c.inner_text().strip() for c in cells]
                    results.append(_normalize_playwright_row(texts))

            log.info("Goochland Playwright: scraped %d rows", len(results))
        except Exception as e:
            log.error("Goochland Playwright scrape failed: %s", e)
        finally:
            browser.close()

    return [r for r in results if r.get("property_zip", "") in TARGET_ZIPS]


def _normalize_energov_record(rec: dict) -> dict:
    """Normalize an EnerGov API record."""
    address = rec.get("address") or rec.get("Address") or {}
    return {
        "source":           "Goochland",
        "permit_number":    rec.get("permitNumber") or rec.get("PermitNumber") or rec.get("id", ""),
        "property_address": _format_address(address) or rec.get("addressFormatted", ""),
        "property_city":    address.get("city") or address.get("City") or "Goochland",
        "property_state":   "VA",
        "property_zip":     (address.get("zip") or address.get("postalCode") or "")[:5],
        "permit_type":      rec.get("permitType") or rec.get("PermitType") or rec.get("type", ""),
        "description":      rec.get("description") or rec.get("Description") or "",
        "file_date":        _parse_date(rec.get("fileDate") or rec.get("FileDate")),
        "job_value_dollars": int(rec.get("jobValue") or rec.get("valuation") or rec.get("Valuation") or 0),
        "owner_name":       rec.get("ownerName") or rec.get("applicantName") or "",
        "contractor_name":  rec.get("contractorName") or "",
    }


def _normalize_playwright_row(cells: list[str]) -> dict:
    return {
        "source":           "Goochland",
        "permit_number":    cells[0] if len(cells) > 0 else "",
        "permit_type":      cells[1] if len(cells) > 1 else "",
        "property_address": cells[2] if len(cells) > 2 else "",
        "property_city":    "Goochland",
        "property_state":   "VA",
        "property_zip":     "",
        "file_date":        cells[3] if len(cells) > 3 else "",
        "description":      cells[4] if len(cells) > 4 else "",
        "job_value_dollars": 0,
        "owner_name":       "",
        "contractor_name":  "",
    }


def _format_address(addr: dict) -> str:
    parts = [
        addr.get("streetNumber") or addr.get("StreetNumber") or "",
        addr.get("streetName") or addr.get("StreetName") or "",
        addr.get("streetSuffix") or addr.get("StreetSuffix") or "",
    ]
    return " ".join(p for p in parts if p).strip()


def _parse_date(val) -> str:
    if not val:
        return ""
    s = str(val)
    return s[:10] if len(s) >= 10 else s
