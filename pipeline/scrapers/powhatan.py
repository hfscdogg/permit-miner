"""
powhatan.py — Powhatan County permit scraper.

Source: Monthly residential permit log PDFs published at:
https://www.powhatanva.gov/209/Residential-Permit-Log-Reports

Strategy:
1. Scrape index page for latest PDF link.
2. Download PDF and extract table with pdfplumber using explicit column boundaries.
3. Merge multi-line rows (addresses/names wrap across rows).
4. All Powhatan addresses are in target ZIPs (23120, 23139, 23153).

Runs monthly (PDFs published ~15th of following month).
"""
import io
import logging
import re

import httpx
import pdfplumber

log = logging.getLogger(__name__)

INDEX_URL = "https://www.powhatanva.gov/209/Residential-Permit-Log-Reports"
BASE_URL = "https://www.powhatanva.gov"

# Column x-boundaries from header word positions (inspected from Feb 2026 PDF).
# Columns: Key | Date | Address | Class+Type | Description | Owner | Contractor | Value | Payments
COL_LINES = [50, 93, 142, 258, 418, 748, 868, 973, 1033, 1100]
COL_KEY = 0
COL_DATE = 1
COL_ADDR = 2
COL_OWNER = 5
COL_CONTRACTOR = 6
COL_VALUE = 7


def fetch_permits(since_days: int = 14) -> list[dict]:
    """Fetch permits from the latest Powhatan residential permit log PDF."""
    pdf_url = _find_latest_pdf_url()
    if not pdf_url:
        log.warning("Powhatan: could not find latest PDF link")
        return []

    log.info("Powhatan: downloading %s", pdf_url)
    try:
        r = httpx.get(pdf_url, follow_redirects=True, timeout=30)
        r.raise_for_status()
    except Exception as e:
        log.error("Powhatan: PDF download failed: %s", e)
        return []

    records = _parse_pdf(r.content)
    log.info("Powhatan: extracted %d permits from PDF", len(records))
    return records


def _find_latest_pdf_url() -> str | None:
    """Scrape index page for the most recent residential permit log PDF link."""
    try:
        r = httpx.get(INDEX_URL, follow_redirects=True, timeout=15)
        r.raise_for_status()
    except Exception as e:
        log.error("Powhatan: could not fetch index page: %s", e)
        return None

    links = re.findall(
        r'href="(/DocumentCenter/View/\d+/[^"]*(?:Residential|RESIDENTIAL)[^"]*)"',
        r.text,
    )
    if not links:
        log.warning("Powhatan: no PDF links found on index page")
        return None

    # Find the most recent year link
    best = None
    for year in ["2027", "2026", "2025", "2024"]:
        year_links = [l for l in links if year in l]
        if year_links:
            best = year_links[-1]
            break
    if not best:
        best = links[-1]

    return f"{BASE_URL}{best}"


def _parse_pdf(content: bytes) -> list[dict]:
    """Extract permit records from PDF using explicit column boundaries."""
    records = []

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            table = page.extract_table({
                "vertical_strategy": "explicit",
                "explicit_vertical_lines": COL_LINES,
                "horizontal_strategy": "text",
                "snap_y_tolerance": 5,
            })
            if table:
                records.extend(_merge_and_extract(table))

    return records


def _merge_and_extract(table: list[list]) -> list[dict]:
    """
    Merge wrapped rows into permit records.

    Permit data wraps across multiple table rows. The 'key' row has the permit
    number in column 0. Preceding non-key rows contain overflow text from the
    address, owner, and contractor columns. We merge backwards from each key row.
    """
    records = []
    pending_addr_parts = []
    pending_owner_parts = []
    pending_contractor_parts = []

    HEADER_WORDS = {"Permit", "Key", "Issue Date", "Address", "Class Description",
                    "Type", "Description", "Owner Name", "Primary Contractor",
                    "Value", "Payments", "Construction", "Total", "TOTALS",
                    "NEW 1", "DWELLING PERMITS"}

    for row in table:
        key_val = (row[COL_KEY] or "").strip()
        date_val = (row[COL_DATE] or "").strip()
        addr_val = (row[COL_ADDR] or "").strip()
        owner_val = (row[COL_OWNER] or "").strip()
        contractor_val = (row[COL_CONTRACTOR] or "").strip()
        value_val = (row[COL_VALUE] or "").strip()

        # Skip header and totals rows
        row_text = " ".join((c or "") for c in row).strip()
        if any(h in row_text for h in HEADER_WORDS) or "TOTALS" in row_text:
            continue

        # Is this a permit key row? (digits only, with a date)
        if re.match(r"^\d{3,10}$", key_val) and re.match(r"\d{1,2}/\d{1,2}/\d{4}", date_val):
            # Build full address from pending parts + this row
            full_addr = " ".join(pending_addr_parts + ([addr_val] if addr_val else []))
            full_owner = " ".join(pending_owner_parts + ([owner_val] if owner_val else []))
            full_contractor = " ".join(pending_contractor_parts + ([contractor_val] if contractor_val else []))

            # Clean up
            full_addr = _clean_text(full_addr)
            full_owner = _clean_name(full_owner)
            full_contractor = _clean_name(full_contractor)

            # Parse value
            value_clean = re.sub(r"[^\d]", "", value_val)
            try:
                job_value = int(value_clean) if value_clean else 0
            except ValueError:
                job_value = 0

            # Skip header/totals rows
            if full_addr and job_value > 0:
                records.append({
                    "source": "Powhatan",
                    "permit_number": key_val,
                    "permit_type": "Residential Building",
                    "property_address": full_addr,
                    "property_city": "Powhatan",
                    "property_state": "VA",
                    "property_zip": "",  # not in PDF — all Powhatan
                    "description": "",
                    "file_date": _normalize_date(date_val),
                    "job_value_dollars": job_value,
                    "owner_name": full_owner.title(),
                    "contractor_name": full_contractor.title(),
                })

            # Reset pending parts
            pending_addr_parts = []
            pending_owner_parts = []
            pending_contractor_parts = []
        else:
            # Accumulate overflow text for the next permit key row
            if addr_val:
                pending_addr_parts.append(addr_val)
            if owner_val:
                pending_owner_parts.append(owner_val)
            if contractor_val:
                pending_contractor_parts.append(contractor_val)

    return records


def _clean_text(text: str) -> str:
    """Remove SINGLE FAMILY / DWELLING noise from address text."""
    text = re.sub(r"\bSINGLE FAMILY\b", "", text, flags=re.IGNORECASE).strip()
    return re.sub(r"\s+", " ", text).strip()


def _clean_name(text: str) -> str:
    """Clean up owner/contractor name — remove fee notes and noise."""
    # Remove dollar amounts and fee notes
    text = re.sub(r"\$[\d.,+= *]+", "", text)
    text = re.sub(r"\*[^*]*\*?", "", text)
    text = re.sub(r"\bSUB FEES\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bOWNER\b$", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_date(val: str) -> str:
    """Convert m/d/yyyy to yyyy-mm-dd."""
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", val)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return val
