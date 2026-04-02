"""
hanover.py — Hanover County permit scraper.

Source: Monthly "Recap of Building Permits Issued" PDFs published at:
https://www.hanovercounty.gov/274/Building-Inspections-Reports-Data

Strategy:
1. Scrape index page for latest "Recap" PDF link.
2. Download PDF and extract text with pdfplumber.
3. Parse structured permit blocks with regex.
4. Filter to RESIDENTIAL BUILDING permits in target ZIPs.

ZIPs: 23005, 23116
Runs monthly (PDFs published ~1st of following month).
"""
import io
import logging
import re

import httpx
import pdfplumber

import config

log = logging.getLogger(__name__)

INDEX_URL = "https://www.hanovercounty.gov/274/Building-Inspections-Reports-Data"
BASE_URL = "https://www.hanovercounty.gov"
TARGET_ZIPS = config.HANOVER_ZIPS


def fetch_permits(since_days: int = 14) -> list[dict]:
    """Fetch permits from the latest Hanover recap PDF."""
    pdf_url = _find_latest_recap_url()
    if not pdf_url:
        log.warning("Hanover: could not find latest Recap PDF link")
        return []

    log.info("Hanover: downloading %s", pdf_url)
    try:
        r = httpx.get(pdf_url, follow_redirects=True, timeout=60)
        r.raise_for_status()
    except Exception as e:
        log.error("Hanover: PDF download failed: %s", e)
        return []

    records = _parse_pdf(r.content)
    log.info("Hanover: extracted %d total permits from PDF", len(records))

    # Filter to residential + target ZIPs
    filtered = [
        r for r in records
        if r.get("permit_type", "").upper().startswith("RESIDENTIAL")
        and _zip_in_targets(r)
    ]
    log.info("Hanover: %d residential permits in target ZIPs", len(filtered))
    return filtered


def _find_latest_recap_url() -> str | None:
    """Find the most recent 'Recap of Building Permits Issued' PDF link."""
    try:
        r = httpx.get(INDEX_URL, follow_redirects=True, timeout=15)
        r.raise_for_status()
    except Exception as e:
        log.error("Hanover: could not fetch index page: %s", e)
        return None

    # Find "Recap" PDF links
    links = re.findall(
        r'href="(/DocumentCenter/View/\d+/[^"]*[Rr]ecap[^"]*)"',
        r.text,
    )
    if not links:
        log.warning("Hanover: no Recap PDF links found")
        return None

    # Take the last one (most recent)
    return f"{BASE_URL}{links[-1]}"


def _parse_pdf(content: bytes) -> list[dict]:
    """Extract permit records from all PDF pages."""
    full_text = ""
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    return _parse_permit_blocks(full_text)


def _parse_permit_blocks(text: str) -> list[dict]:
    """
    Parse structured permit blocks from Hanover recap PDF.

    Each permit block has this pattern:
        BC2026-00033 COMMERCIAL BUILDING 11505 Field House WAY $1,500,000.00
        2/3/2026 NEW 7777-99-1005 $8,083.93
        3/5/2026 ISSUED Chickahominy Falls $8,083.93
        Contact Type Contact Name Contact Address Phone Number
        APPLICANT ...
        CONTRACTOR ...
        OWNER ...
    """
    records = []

    # Split into permit blocks starting with permit number pattern
    # BC20XX-XXXXX or similar
    block_pattern = re.compile(
        r"^((?:BC|BR|BE|BM)\d{4}-\d{4,6})\s+(.+?)\s+\$([\d,.]+)\s*$",
        re.MULTILINE,
    )

    matches = list(block_pattern.finditer(text))

    for i, m in enumerate(matches):
        permit_number = m.group(1)
        type_and_address = m.group(2).strip()
        valuation_str = m.group(3).replace(",", "")

        # Parse permit type and address from "RESIDENTIAL BUILDING 123 Main ST"
        permit_type, address = _split_type_address(type_and_address)

        # Get the text between this match and the next one for additional fields
        block_start = m.end()
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block_text = text[block_start:block_end]

        # Parse line 2: applied_date subtype parcel $fees
        subtype = ""
        applied_date = ""
        line2_match = re.search(
            r"^(\d{1,2}/\d{1,2}/\d{4})\s+(\S+.*?)\s+\d{4}-\d{2}-\d{4}",
            block_text, re.MULTILINE,
        )
        if line2_match:
            applied_date = line2_match.group(1)
            subtype = line2_match.group(2).strip()

        # Parse line 3: issued_date status subdivision $paid
        issued_date = ""
        line3_match = re.search(
            r"^(\d{1,2}/\d{1,2}/\d{4})\s+(ISSUED|FINALED|EXPIRED|VOIDED|ACTIVE)",
            block_text, re.MULTILINE,
        )
        if line3_match:
            issued_date = line3_match.group(1)

        # Parse contacts
        owner_name = ""
        contractor_name = ""
        owner_address = ""

        owner_match = re.search(
            r"^OWNER\s+(.+?)(?:\s+\(|$)",
            block_text, re.MULTILINE,
        )
        if owner_match:
            owner_line = owner_match.group(1).strip()
            owner_name, owner_address = _split_contact_name_address(owner_line)

        contractor_match = re.search(
            r"^CONTRACTOR\s+(.+?)(?:\s+\(|$)",
            block_text, re.MULTILINE,
        )
        if contractor_match:
            contractor_name = contractor_match.group(1).strip()
            contractor_name, _ = _split_contact_name_address(contractor_name)

        # Extract ZIP from owner address
        owner_zip = ""
        zip_match = re.search(r"\b(\d{5})\b", owner_address)
        if zip_match:
            owner_zip = zip_match.group(1)

        # Also try to get ZIP from the address line in contact rows
        property_zip = _extract_zip_from_block(block_text)

        try:
            valuation = int(float(valuation_str))
        except ValueError:
            valuation = 0

        records.append({
            "source": "Hanover",
            "permit_number": permit_number,
            "permit_type": permit_type,
            "permit_subtype": subtype,
            "property_address": address,
            "property_city": "Hanover",
            "property_state": "VA",
            "property_zip": property_zip,
            "description": subtype,
            "file_date": _normalize_date(applied_date or issued_date),
            "job_value_dollars": valuation,
            "owner_name": owner_name,
            "contractor_name": contractor_name,
        })

    return records


def _split_type_address(raw: str) -> tuple[str, str]:
    """Split 'RESIDENTIAL BUILDING 123 Main ST' into type and address."""
    # Known permit types
    for ptype in ["RESIDENTIAL BUILDING", "COMMERCIAL BUILDING"]:
        if raw.upper().startswith(ptype):
            address = raw[len(ptype):].strip()
            return ptype.title(), address
    # Fallback
    parts = raw.split(None, 2)
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1]}".title(), parts[2]
    return raw.title(), ""


def _split_contact_name_address(raw: str) -> tuple[str, str]:
    """Split 'JOHN DOE 123 MAIN ST RICHMOND, VA 23226' into name and address."""
    # Look for the start of a street address (number followed by word)
    m = re.search(r"\b(\d+\s+[A-Z])", raw)
    if m:
        name = raw[:m.start()].strip()
        address = raw[m.start():].strip()
        if name:
            return name.title(), address
    # No address found
    return raw.title(), ""


def _extract_zip_from_block(block_text: str) -> str:
    """Extract ZIP code from contact address lines in the permit block."""
    # Look for VA ZIP codes in APPLICANT or OWNER lines
    for pattern in [r"APPLICANT\s+.+?\bVA\s+(\d{5})", r"OWNER\s+.+?\bVA\s+(\d{5})"]:
        m = re.search(pattern, block_text, re.IGNORECASE)
        if m:
            return m.group(1)
    return ""


def _zip_in_targets(record: dict) -> bool:
    """Check if a permit's ZIP matches target ZIPs."""
    z = record.get("property_zip", "")
    if z and z in TARGET_ZIPS:
        return True
    # If no ZIP extracted, we can't filter — skip it
    return False


def _normalize_date(val: str) -> str:
    """Convert m/d/yyyy to yyyy-mm-dd."""
    if not val:
        return ""
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", val)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return val
