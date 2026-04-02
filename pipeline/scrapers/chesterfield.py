"""
chesterfield.py — Chesterfield County permit scraper.

Portal: Accela Citizen Access (ACA)
URL: https://aca-prod.accela.com/CHESTERFIELD/

Strategy:
1. Use Playwright to search the ACA portal for Residential Building permits.
2. Scrape the results table page by page (5 rows per page).
3. Parse addresses and filter to target ZIPs.

ZIPs: 23113, 23114, 23146, 23838
"""
import logging
import re
from datetime import date, timedelta

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

# Results table selectors
TABLE_ID = "ctl00_PlaceHolderMain_dgvPermitList_gdvPermitList"
ROW_SELECTOR = "tr.ACA_TabRow_Odd, tr.ACA_TabRow_Even"

# Column indices (0-based, from header inspection):
# 0: checkbox, 1: Created Date, 2: Record Number, 3: Record Type,
# 4: Action, 5: Address, 6: Description of Work, 7: Project Name, 8: Status, 9: (hidden)
COL_DATE = 1
COL_RECORD_NUM = 2
COL_RECORD_TYPE = 3
COL_ADDRESS = 5
COL_DESCRIPTION = 6
COL_PROJECT = 7
COL_STATUS = 8

MAX_PAGES = 20  # Safety limit


def fetch_permits(since_days: int = 14) -> list[dict]:
    """Fetch Chesterfield residential building permits filed in the last `since_days` days."""
    date_from = (date.today() - timedelta(days=since_days)).strftime("%m/%d/%Y")
    date_to = date.today().strftime("%m/%d/%Y")
    log.info("Chesterfield: fetching permits %s to %s", date_from, date_to)

    rows = _scrape_via_playwright(date_from, date_to)
    if rows is None:
        log.warning("Chesterfield: scrape failed, returning empty list")
        return []

    # Filter to target ZIPs
    filtered = [r for r in rows if r.get("property_zip", "") in TARGET_ZIPS]
    log.info("Chesterfield: %d permits total, %d in target ZIPs", len(rows), len(filtered))
    return filtered


def _scrape_via_playwright(date_from: str, date_to: str) -> list[dict] | None:
    """
    Use Playwright to:
    1. Navigate to ACA Building search
    2. Select 'Residential Building' record type
    3. Fill date range
    4. Click Search
    5. Scrape results table, paginating through all pages
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("Playwright not installed — run: pip install playwright && playwright install chromium")
        return None

    all_records = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
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
            body_text = page.text_content("body") or ""
            if "Record results matching" not in body_text:
                log.warning("Chesterfield: no results found after search")
                return []

            # Step 5: Scrape all pages
            for page_num in range(1, MAX_PAGES + 1):
                records = _extract_table_rows(page)
                all_records.extend(records)
                log.debug("Chesterfield: page %d — %d rows", page_num, len(records))

                # Check for Next page link
                next_link = page.query_selector("a:has-text('Next >')")
                if not next_link:
                    break
                next_link.click()
                page.wait_for_load_state("networkidle", timeout=15000)

            log.info("Chesterfield: scraped %d total rows across %d pages",
                     len(all_records), page_num)

        except Exception as e:
            log.error("Chesterfield Playwright scrape failed: %s", e)
            # Return whatever we've collected so far
            if all_records:
                log.info("Chesterfield: returning %d partial results", len(all_records))
                return all_records
            return None
        finally:
            browser.close()

    return all_records


def _extract_table_rows(page) -> list[dict]:
    """Extract permit records from the current results page."""
    records = []
    table = page.query_selector(f"#{TABLE_ID}")
    if not table:
        return records

    rows = table.query_selector_all(ROW_SELECTOR)
    for row in rows:
        cells = row.query_selector_all("td")
        if len(cells) < 9:
            continue

        texts = [c.inner_text().strip() for c in cells]

        address_raw = texts[COL_ADDRESS]
        if not address_raw or address_raw == "United States":
            continue

        parsed = _parse_address(address_raw)
        if not parsed["zip"]:
            continue

        records.append({
            "source": "Chesterfield",
            "permit_number": texts[COL_RECORD_NUM],
            "permit_type": texts[COL_RECORD_TYPE],
            "property_address": parsed["street"],
            "property_city": parsed["city"],
            "property_state": "VA",
            "property_zip": parsed["zip"],
            "description": texts[COL_DESCRIPTION],
            "file_date": _parse_date(texts[COL_DATE]),
            "project_name": texts[COL_PROJECT],
            "status": texts[COL_STATUS],
            "job_value_dollars": 0,
            "owner_name": "",
            "contractor_name": "",
        })

    return records


def _parse_address(raw: str) -> dict:
    """
    Parse Accela address format: '5409 QUALLA TRACE TER, Chesterfield VA 23832'
    Returns dict with street, city, zip.
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
