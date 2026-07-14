"""
spotsylvania.py — Spotsylvania County permit scraper.

Source: Monthly Permit Report PDFs published in the county's CivicPlus
Archive Center:
    https://www.spotsylvania.va.us/Archive.aspx?AMID=47
    (linked from https://www.spotsylvania.va.us/763/Monthly-Permit-Reports)

Report columns: PERMIT NUMBER | PERMIT TYPE | APPLICANT NAME | ADDRESS |
ISSUED DATE | PERMIT SUBTYPE. Generated PDFs (not scans), so pdfplumber
table/text extraction should work without OCR.

ZIPs: 22407, 22553 (Fredericksburg-area territory)
Cadence: monthly.

Debug (run from GitHub Actions via the Scraper Debug workflow —
local egress may be blocked):
    python -m pipeline.scrapers.spotsylvania
"""
import io
import logging
import re

import httpx
import pdfplumber

import config

log = logging.getLogger(__name__)

INDEX_URL = "https://www.spotsylvania.va.us/Archive.aspx?AMID=47"
BASE_URL = "https://www.spotsylvania.va.us"
TARGET_ZIPS = config.SPOTSYLVANIA_ZIPS

# CivicPlus WAF blocks non-browser user agents
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_permits(since_days: int = 14) -> list[dict]:
    """Fetch permits from the latest Spotsylvania monthly report PDFs."""
    items = _find_report_items()
    if not items:
        log.warning("Spotsylvania: no monthly permit reports found in Archive Center")
        return []

    records: list[dict] = []
    # Latest two reports cover the month boundary on weekly runs;
    # address-level dedup downstream makes re-reads safe.
    for url, label in items[:2]:
        log.info("Spotsylvania: downloading %s (%s)", url, label)
        try:
            r = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=60)
            r.raise_for_status()
        except Exception as e:
            log.error("Spotsylvania: PDF download failed for %s: %s", url, e)
            continue
        if not r.content[:5].startswith(b"%PDF"):
            log.warning("Spotsylvania: %s did not return a PDF (got %s)",
                        url, r.headers.get("content-type"))
            continue
        parsed = _parse_pdf(r.content)
        log.info("Spotsylvania: extracted %d records from %s", len(parsed), label)
        records.extend(parsed)

    filtered = [r for r in records if _zip_in_targets(r)]
    log.info("Spotsylvania: %d permits in target ZIPs (of %d total)",
             len(filtered), len(records))
    return filtered


def _find_report_items() -> list[tuple[str, str]]:
    """Return [(pdf_url, label)] for monthly permit reports, newest first."""
    try:
        r = httpx.get(INDEX_URL, headers=HEADERS, follow_redirects=True, timeout=30)
        r.raise_for_status()
    except Exception as e:
        log.error("Spotsylvania: could not fetch Archive Center listing: %s", e)
        return []
    return _extract_report_items(r.text)


def _extract_report_items(html: str) -> list[tuple[str, str]]:
    items: list[tuple[int, str, str]] = []
    for m in re.finditer(
        r"""<a[^>]+href\s*=\s*["']([^"']*(?:ADID=|ViewFile/Item/)(\d+)[^"']*)["'][^>]*>(.*?)</a>""",
        html, re.IGNORECASE | re.DOTALL,
    ):
        adid = int(m.group(2))
        label = re.sub(r"<[^>]+>", "", m.group(3)).strip()
        items.append((adid, f"{BASE_URL}/ArchiveCenter/ViewFile/Item/{adid}", label))

    seen: set[int] = set()
    unique: list[tuple[int, str, str]] = []
    for adid, url, label in items:
        if adid in seen:
            continue
        seen.add(adid)
        low = label.lower()
        # Skip the running "Total Dwellings & Permits" count summary
        if "total" in low or "dwelling" in low:
            continue
        if "permit" in low or not label:
            unique.append((adid, url, label))

    unique.sort(key=lambda t: t[0], reverse=True)
    return [(url, label or f"item {adid}") for adid, url, label in unique]


def _parse_pdf(content: bytes) -> list[dict]:
    """Extract permit records — table extraction first, text-line fallback."""
    records: list[dict] = []
    full_text = ""

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        header: list[str] | None = None
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                # Continuation pages may repeat or omit the header row
                if _looks_like_header(table[0]):
                    header = [(c or "").strip().lower() for c in table[0]]
                    rows = table[1:]
                else:
                    rows = table
                if header:
                    records.extend(_parse_table_rows(header, rows))
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    if not records and full_text:
        records = _parse_text_lines(full_text)

    return records


def _looks_like_header(row: list) -> bool:
    joined = " ".join((c or "") for c in row).lower()
    return "permit" in joined and ("number" in joined or "type" in joined)


def _parse_table_rows(header: list[str], rows: list[list]) -> list[dict]:
    def col(*keywords, exclude=()) -> int | None:
        for i, h in enumerate(header):
            if any(k in h for k in keywords) and not any(x in h for x in exclude):
                return i
        return None

    c_num     = col("number")
    c_type    = col("permit type", "type", exclude=("subtype", "sub type"))
    c_subtype = col("subtype", "sub type")
    c_appl    = col("applicant", "name", exclude=("subtype",))
    c_addr    = col("address", "location")
    c_date    = col("issued", "date")

    def cell(row: list, idx: int | None) -> str:
        if idx is None or idx >= len(row):
            return ""
        return (row[idx] or "").replace("\n", " ").strip()

    records = []
    for row in rows:
        if not any(row):
            continue
        address = cell(row, c_addr)
        if not address or not re.search(r"\d", address):
            continue
        records.append(_make_record(
            permit_number=cell(row, c_num),
            permit_type=cell(row, c_type),
            subtype=cell(row, c_subtype),
            applicant=cell(row, c_appl),
            address=address,
            issued_date=cell(row, c_date),
        ))
    return records


def _parse_text_lines(text: str) -> list[dict]:
    """
    Fallback: lines shaped like
        B2400123 RESIDENTIAL SMITH JOHN 123 LAKE DR FREDERICKSBURG VA 22407 6/12/2026 POOL
    Only requires a permit-number-ish token, an address, and a date.
    """
    records = []
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < 20:
            continue
        date_m = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})", line)
        num_m = re.match(r"([A-Z]{0,4}\d{2,4}[-]?\d{3,6})\s+", line)
        addr_m = re.search(r"\b(\d{1,6}\s+[A-Z][A-Za-z0-9 .'-]+?)(?=\s+\d{1,2}/|\s{2,}|$)", line)
        if not (date_m and addr_m):
            continue
        records.append(_make_record(
            permit_number=num_m.group(1) if num_m else "",
            permit_type=line[num_m.end():addr_m.start()].strip() if num_m else "",
            subtype="",
            applicant="",
            address=addr_m.group(1).strip(),
            issued_date=date_m.group(1),
        ))
    return records


def _make_record(permit_number, permit_type, subtype, applicant,
                 address, issued_date) -> dict:
    # Applicant may be the homeowner or a company — route companies to
    # contractor_name so the owner-type filter doesn't drop the permit.
    owner_name = ""
    contractor_name = ""
    if applicant:
        upper = f" {applicant.upper()} "
        if any(pat in upper for pat in config.COMPANY_PATTERNS):
            contractor_name = applicant.title()
        else:
            owner_name = applicant.title()

    description = f"{permit_type} {subtype}".strip()
    return {
        "source": "Spotsylvania",
        "permit_number": permit_number,
        "permit_type": permit_type or "Residential Building",
        "property_address": _street_only(address),
        "property_city": "Fredericksburg",
        "property_state": "VA",
        "property_zip": _extract_zip(address),
        "description": description,
        "file_date": _normalize_date(issued_date),
        "job_value_dollars": 0,
        "owner_name": owner_name,
        "contractor_name": contractor_name,
    }


def _street_only(address: str) -> str:
    """Trim city/state/ZIP tail if present; keep the street line."""
    addr = re.split(r",", address)[0].strip()
    addr = re.sub(r"\s+(FREDERICKSBURG|SPOTSYLVANIA|PARTLOW|THORNBURG)\b.*$", "",
                  addr, flags=re.IGNORECASE).strip()
    return addr


def _extract_zip(text: str) -> str:
    m = re.search(r"\b(22\d{3})\b", text)
    return m.group(1) if m else ""


def _zip_in_targets(record: dict) -> bool:
    return record.get("property_zip", "") in TARGET_ZIPS


def _normalize_date(val: str) -> str:
    if not val:
        return ""
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", val)
    if m:
        year = m.group(3)
        if len(year) == 2:
            year = f"20{year}"
        return f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return val


# ── Debug entrypoint ──────────────────────────────────────────────────────────

def _debug():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")
    print("=== Archive Center items ===")
    r = httpx.get(INDEX_URL, headers=HEADERS, follow_redirects=True, timeout=30)
    print(f"listing HTTP {r.status_code}, {len(r.text)} chars")
    items = _extract_report_items(r.text)
    for url, label in items[:12]:
        print(f"  {label}  ->  {url}")
    if not items:
        print("  (none found) — dumping anchors for diagnosis:")
        anchors = re.findall(r"<a[^>]+href[^>]*>.*?</a>", r.text, re.IGNORECASE | re.DOTALL)
        for a in anchors:
            flat = " ".join(a.split())
            if re.search(r"archive|viewfile|adid|permit|report", flat, re.IGNORECASE):
                print(f"  ANCHOR: {flat[:250]}")
        return

    url, label = items[0]
    print(f"\n=== Downloading latest: {label} ===")
    r = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=60)
    print(f"HTTP {r.status_code}  content-type={r.headers.get('content-type')}  bytes={len(r.content)}")
    if not r.content[:5].startswith(b"%PDF"):
        print("Not a PDF — first 500 bytes:")
        print(r.content[:500])
        return

    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        print(f"\n=== PDF has {len(pdf.pages)} pages ===")
        for i, page in enumerate(pdf.pages[:2]):
            print(f"\n--- Page {i+1} raw text (first 3000 chars) ---")
            print((page.extract_text() or "(no text extracted)")[:3000])
            table = page.extract_table()
            if table:
                print(f"\n--- Page {i+1} table ({len(table)} rows, first 10) ---")
                for row in table[:10]:
                    print(f"  {row}")

    records = _parse_pdf(r.content)
    print(f"\n=== Parsed {len(records)} records (first 10) ===")
    for rec in records[:10]:
        print(f"  {rec}")
    kept = [rec for rec in records if _zip_in_targets(rec)]
    print(f"\n=== {len(kept)} in target ZIPs (first 10) ===")
    for rec in kept[:10]:
        print(f"  {rec}")


if __name__ == "__main__":
    _debug()
