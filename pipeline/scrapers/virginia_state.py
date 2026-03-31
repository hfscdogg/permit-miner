"""
virginia_state.py — Virginia statewide building permit CSV scraper.

Source: data.virginia.gov Building Permits dataset.
This is tested first as a potential single-source replacement for
most county scrapers. Covers residential permits statewide.

Returns a list of normalized permit dicts.
"""
import csv
import io
import logging
from datetime import date, timedelta

import httpx

import config

log = logging.getLogger(__name__)

# Columns we care about in the state CSV (actual names vary — mapped below)
FIELD_MAP = {
    # Try these column names in order
    "permit_number":  ["permit_number", "PermitNumber", "Permit Number", "permit_no"],
    "address":        ["address", "Address", "property_address", "site_address", "SiteAddress"],
    "city":           ["city", "City", "municipality", "Municipality"],
    "zip":            ["zip", "Zip", "zip_code", "ZipCode", "postal_code"],
    "permit_type":    ["permit_type", "PermitType", "Permit Type", "type", "Type"],
    "description":    ["description", "Description", "work_description"],
    "issue_date":     ["issue_date", "IssueDate", "Issue Date", "file_date", "FileDate", "issued_date"],
    "job_value":      ["job_value", "JobValue", "Job Value", "valuation", "Valuation", "estimated_value"],
    "owner_name":     ["owner_name", "OwnerName", "Owner", "applicant_name", "ApplicantName"],
    "contractor":     ["contractor", "Contractor", "contractor_name", "ContractorName"],
    "county":         ["county", "County", "locality", "Locality", "jurisdiction"],
}

TARGET_ZIPS = set(config.ZIP_CODES)


def _pick_col(headers: list[str], candidates: list[str]) -> str | None:
    """Return the first candidate column name found in headers (case-insensitive)."""
    lower_headers = {h.lower(): h for h in headers}
    for c in candidates:
        if c.lower() in lower_headers:
            return lower_headers[c.lower()]
    return None


def _build_col_index(headers: list[str]) -> dict[str, str | None]:
    return {field: _pick_col(headers, candidates) for field, candidates in FIELD_MAP.items()}


def _val(row: dict, col: str | None) -> str:
    if col is None:
        return ""
    return (row.get(col) or "").strip()


def fetch_permits(since_days: int = 14) -> list[dict]:
    """
    Download the Virginia state CSV and return permits in our ZIP territory
    filed within the last `since_days` days.
    """
    log.info("Fetching Virginia state permit CSV...")
    try:
        r = httpx.get(config.VA_STATE_CSV_URL, timeout=120, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.error("Virginia state CSV download failed: %s", e)
        return []

    text = r.text
    log.info("Downloaded %d bytes", len(text))

    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    log.info("CSV columns: %s", headers[:20])

    col = _build_col_index(headers)
    log.debug("Column mapping: %s", {k: v for k, v in col.items() if v})

    cutoff = (date.today() - timedelta(days=since_days)).isoformat()
    results = []
    total_rows = zip_miss = date_miss = 0

    for row in reader:
        total_rows += 1
        zip_val = _val(row, col["zip"])
        if zip_val[:5] not in TARGET_ZIPS:
            zip_miss += 1
            continue

        issue_date = _val(row, col["issue_date"])
        if issue_date and issue_date < cutoff:
            date_miss += 1
            continue

        owner = _val(row, col["owner_name"])
        address = _val(row, col["address"])
        if not address:
            continue

        results.append({
            "source":            "Virginia State",
            "permit_number":     _val(row, col["permit_number"]),
            "property_address":  address,
            "property_city":     _val(row, col["city"]),
            "property_state":    "VA",
            "property_zip":      zip_val[:5],
            "permit_type":       _val(row, col["permit_type"]),
            "description":       _val(row, col["description"]),
            "file_date":         issue_date,
            "job_value_dollars": _parse_dollars(_val(row, col["job_value"])),
            "owner_name":        owner,
            "contractor_name":   _val(row, col["contractor"]),
            "county":            _val(row, col["county"]),
        })

    log.info(
        "Virginia CSV: %d total rows, %d in territory, %d filtered by date/zip (zip_miss=%d, date_miss=%d)",
        total_rows, len(results), zip_miss + date_miss, zip_miss, date_miss,
    )
    return results


def _parse_dollars(val: str) -> int:
    """Parse '$125,000' or '125000' → int dollars. Returns 0 on failure."""
    if not val:
        return 0
    cleaned = val.replace("$", "").replace(",", "").strip()
    try:
        return int(float(cleaned))
    except ValueError:
        return 0
