"""
chesterfield.py — Chesterfield County permit scraper.

Portal: Accela Citizen Access (ACA)
URL: https://aca-prod.accela.com/CHESTERFIELD/

Strategy:
1. Use Playwright to search the ACA portal for Residential Building permits.
2. Click "Download results" to get a CSV of all matches (no pagination needed).
3. Parse the CSV and filter to target ZIPs.

ZIPs: 23113, 23114, 23146, 23838
"""
import csv
import io
import logging
import re
import tempfile
from datetime import date, timedelta
from pathlib import Path

import config

log = logging.getLogger(__name__)

ACA_BASE = "https://aca-prod.accela.com/CHESTERFIELD"
SEARCH_URL = f"{ACA_BASE}/Cap/CapHome.aspx?module=Building"
TARGET_ZIPS = config.CHESTERFIELD_ZIPS

# Accela ACA element IDs (inspected from live DOM 2026-04-02)
RECORD_TYPE_DROPDOWN = "ctl00_PlaceHolderMain_generalSearchForm_ddlGSPermitType"
RECORD_TYPE_VALUE = "Building/Permit/Residential/NA"
DATE_FROM_ID = "ctl00_PlaceHolderMain_generalSearchForm_txtGSStartDate"
DATE_TO_ID = "ctl00_PlaceHolderMain_generalSearchForm_txtGSEndDate"
SEARCH_BTN_ID = "ctl00_PlaceHolderMain_btnNewSearch"
DOWNLOAD_LINK_ID = "ctl00_PlaceHolderMain_dgvPermitList_gdvPermitList_gdvPermitListtop4btnExport"


def fetch_permits(since_days: int = 14) -> list[dict]:
    """Fetch Chesterfield residential building permits filed in the last `since_days` days."""
    date_from = (date.today() - timedelta(days=since_days)).strftime("%m/%d/%Y")
    date_to = date.today().strftime("%m/%d/%Y")
    log.info("Chesterfield: fetching permits %s to %s", date_from, date_to)

    rows = _download_csv_via_playwright(date_from, date_to)
    if rows is None:
        log.warning("Chesterfield: scrape failed, returning empty list")
        return []

    # Filter to target ZIPs
    filtered = [r for r in rows if r.get("property_zip", "") in TARGET_ZIPS]
    log.info("Chesterfield: %d permits total, %d in target ZIPs", len(rows), len(filtered))
    return filtered


def _download_csv_via_playwright(date_from: str, date_to: str) -> list[dict] | None:
    """
    Use Playwright to:
    1. Navigate to ACA Building search
    2. Select 'Residential Building' record type
    3. Fill date range
    4. Click Search
    5. Click 'Download results' to get CSV
    6. Parse and return normalized records
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("Playwright not installed — run: pip install playwright && playwright install chromium")
        return None

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        try:
            # Step 1: Navigate to search page
            page.goto(SEARCH_URL, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

            # Step 2: Select "Residential Building" record type
            page.select_option(f"#{RECORD_TYPE_DROPDOWN}", value=RECORD_TYPE_VALUE)

            # Step 3: Fill date range (mm/dd/yyyy format)
            page.fill(f"#{DATE_FROM_ID}", date_from)
            page.fill(f"#{DATE_TO_ID}", date_to)

            # Step 4: Click Search
            page.click(f"#{SEARCH_BTN_ID}")
            page.wait_for_load_state("networkidle", timeout=30000)

            # Verify results appeared
            results_text = page.text_content("body")
            if "Record results matching" not in (results_text or ""):
                log.warning("Chesterfield: no results found after search")
                return []

            # Step 5: Click "Download results" and capture the CSV download
            with page.expect_download(timeout=30000) as download_info:
                page.click(f"#{DOWNLOAD_LINK_ID}")
            download = download_info.value

            # Save to temp file and parse
            tmp_path = Path(tempfile.mkdtemp()) / "chesterfield_permits.csv"
            download.save_as(str(tmp_path))
            log.info("Chesterfield: CSV downloaded to %s", tmp_path)

            records = _parse_csv(tmp_path)

            # Cleanup
            tmp_path.unlink(missing_ok=True)
            return records

        except Exception as e:
            log.error("Chesterfield Playwright scrape failed: %s", e)
            return None
        finally:
            browser.close()


def _parse_csv(csv_path: Path) -> list[dict]:
    """Parse the Accela ACA CSV export into normalized permit dicts."""
    records = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            address_raw = (row.get("Address") or "").strip()
            if not address_raw or address_raw == "United States":
                continue

            parsed = _parse_address(address_raw)
            if not parsed["zip"]:
                continue

            records.append({
                "source": "Chesterfield",
                "permit_number": (row.get("Record Number") or "").strip(),
                "permit_type": (row.get("Record Type") or "").strip(),
                "property_address": parsed["street"],
                "property_city": parsed["city"],
                "property_state": "VA",
                "property_zip": parsed["zip"],
                "description": (row.get("Description of Work") or "").strip(),
                "file_date": _parse_date(row.get("Created Date", "")),
                "project_name": (row.get("Project Name") or "").strip(),
                "status": (row.get("Status") or "").strip(),
                "job_value_dollars": 0,
                "owner_name": "",
                "contractor_name": "",
            })

    return records


def _parse_address(raw: str) -> dict:
    """
    Parse Accela address format: '5409 QUALLA TRACE TER, Chesterfield VA 23832'
    Returns dict with street, city, state, zip.
    """
    # Pattern: street, city STATE zip
    match = re.match(r"^(.+?),\s*(.+?)\s+VA\s+(\d{5})\s*$", raw, re.IGNORECASE)
    if match:
        return {
            "street": match.group(1).strip(),
            "city": match.group(2).strip(),
            "zip": match.group(3),
        }

    # Fallback: try to extract ZIP from end
    zip_match = re.search(r"\b(\d{5})\s*$", raw)
    if zip_match:
        return {
            "street": raw[:zip_match.start()].rstrip(", "),
            "city": "",
            "zip": zip_match.group(1),
        }

    return {"street": raw, "city": "", "zip": ""}


def _parse_date(val: str) -> str:
    """Convert mm/dd/yyyy to yyyy-mm-dd."""
    val = val.strip()
    match = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", val)
    if match:
        return f"{match.group(3)}-{match.group(1)}-{match.group(2)}"
    return val
