"""
chesterfield.py — Chesterfield County permit scraper.

Portal: Accela Citizen Access (ACA)
URL: https://aca-prod.accela.com/CHESTERFIELD/

Strategy:
1. Try the Accela public JSON API endpoints first (fast, no JS required).
2. Fall back to Playwright browser automation if JSON endpoints change.

ZIPs: 23113, 23114, 23146, 23838
"""
import logging
from datetime import date, timedelta

import httpx

import config

log = logging.getLogger(__name__)

ACA_BASE = "https://aca-prod.accela.com/CHESTERFIELD"
TARGET_ZIPS = config.CHESTERFIELD_ZIPS

# Accela ELM search endpoint (undocumented public API)
# These cap module names may vary — residential building is typically "Building"
ACA_SEARCH_URL = f"{ACA_BASE}/Cap/CapList.aspx"
ACA_API_URL = f"{ACA_BASE}/api/cap/search"


def fetch_permits(since_days: int = 14) -> list[dict]:
    """Fetch Chesterfield building permits filed in the last `since_days` days."""
    cutoff = (date.today() - timedelta(days=since_days)).isoformat()
    log.info("Chesterfield: fetching permits since %s", cutoff)

    results = _try_json_api(cutoff)
    if results is not None:
        log.info("Chesterfield: %d permits via JSON API", len(results))
        return results

    log.info("Chesterfield: JSON API unavailable, falling back to Playwright")
    return _try_playwright(cutoff)


def _try_json_api(cutoff: str) -> list[dict] | None:
    """
    Attempt Accela's undocumented JSON endpoints.
    Returns None if the endpoint is inaccessible (triggering Playwright fallback).
    """
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; PermitMiner/1.0)",
    }

    # Try Accela's Automation REST API (available on some installations)
    try:
        # Search for residential building permits
        params = {
            "module": "Building",
            "status": "Issued",
            "fileDate.from": cutoff,
            "pageSize": 200,
            "pageNumber": 1,
        }
        r = httpx.get(
            f"{ACA_BASE}/api/v4/caps",
            headers=headers,
            params=params,
            timeout=30,
            follow_redirects=True,
        )
        if r.status_code == 200:
            data = r.json()
            records = data.get("result") or data.get("records") or []
            if records:
                return [_normalize_accela_record(rec) for rec in records]
    except Exception as e:
        log.debug("Chesterfield JSON API attempt failed: %s", e)

    return None


def _try_playwright(cutoff: str) -> list[dict]:
    """
    Playwright-based scraper for Accela ACA portal.
    Navigates to the permit search page and extracts results.
    """
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
            # Navigate to permit search
            page.goto(f"{ACA_BASE}/Cap/CapList.aspx?module=Building", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

            # Fill date range
            # Accela ACA typically has "File Date From" and "File Date To" fields
            try:
                page.fill('input[id*="txtFileDate"]', cutoff)
                page.click('input[id*="btnSearch"]')
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                log.debug("Chesterfield: could not interact with date fields")
                return []

            # Extract table rows
            rows = page.query_selector_all("table.dataGridList tr[class*='GridItem']")
            for row in rows:
                cells = row.query_selector_all("td")
                if len(cells) < 4:
                    continue
                texts = [c.inner_text().strip() for c in cells]
                results.append(_normalize_playwright_row(texts))

            log.info("Chesterfield Playwright: scraped %d rows", len(results))
        except Exception as e:
            log.error("Chesterfield Playwright scrape failed: %s", e)
        finally:
            browser.close()

    return [r for r in results if r.get("property_zip", "") in TARGET_ZIPS]


def _normalize_accela_record(rec: dict) -> dict:
    """Normalize an Accela REST API record to our standard permit dict."""
    address = rec.get("address") or {}
    applicant = rec.get("applicantInformation") or {}
    return {
        "source":           "Chesterfield",
        "permit_number":    rec.get("id", {}).get("customId") or rec.get("id", {}).get("value", ""),
        "property_address": _format_address(address),
        "property_city":    address.get("city", ""),
        "property_state":   address.get("state", {}).get("value", "VA"),
        "property_zip":     address.get("postalCode", "")[:5],
        "permit_type":      rec.get("type", {}).get("value", ""),
        "description":      rec.get("description", ""),
        "file_date":        _parse_accela_date(rec.get("fileDate")),
        "job_value_dollars": int(rec.get("estimatedValuation", 0) or 0),
        "owner_name":       applicant.get("lastName", "") + " " + applicant.get("firstName", ""),
        "contractor_name":  "",
    }


def _normalize_playwright_row(cells: list[str]) -> dict:
    """Normalize a scraped table row. Column order varies by ACA install."""
    # Typical column order: Permit #, Type, Address, Status, File Date, Description
    return {
        "source":           "Chesterfield",
        "permit_number":    cells[0] if len(cells) > 0 else "",
        "permit_type":      cells[1] if len(cells) > 1 else "",
        "property_address": cells[2] if len(cells) > 2 else "",
        "property_city":    "Chesterfield",
        "property_state":   "VA",
        "property_zip":     "",
        "file_date":        cells[4] if len(cells) > 4 else "",
        "description":      cells[5] if len(cells) > 5 else "",
        "job_value_dollars": 0,
        "owner_name":       "",
        "contractor_name":  "",
    }


def _format_address(addr: dict) -> str:
    parts = [
        addr.get("streetStart", ""),
        addr.get("streetDirection", {}).get("value", ""),
        addr.get("streetName", ""),
        addr.get("streetSuffix", {}).get("value", ""),
    ]
    return " ".join(p for p in parts if p).strip()


def _parse_accela_date(val) -> str:
    if not val:
        return ""
    if isinstance(val, str):
        return val[:10]
    if isinstance(val, dict):
        return str(val.get("value", ""))[:10]
    return str(val)[:10]
