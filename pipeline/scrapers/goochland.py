"""
goochland.py — Goochland County permit scraper.

Source: Monthly "Permits Issued" report PDFs published in the county's
CivicPlus Archive Center (available May 2024 onward):
    https://www.goochlandva.us/Archive.aspx?AMID=60

The EnerGov portal still requires Tyler Identity SSO login (no public
search), but these monthly PDFs are public — same pattern as Powhatan
and Hanover.

Strategy:
1. Fetch the Archive Center listing (browser User-Agent required —
   CivicPlus returns 403 to non-browser clients).
2. Find "Permits Issued" archive items, take the most recent two
   (covers the month boundary on weekly runs).
3. Download each PDF and extract records via pdfplumber — table
   extraction first, text-line fallback.
4. Filter to residential permits in target ZIPs (23103 Manakin-Sabot,
   23129 Oilville). ZIPs are inferred from city names when the PDF
   omits them.

Debug (prints raw PDF text + parsed records; run from GitHub Actions
via the Scraper Debug workflow since local egress may be blocked):
    python -m pipeline.scrapers.goochland
"""
import io
import logging
import re

import httpx
import pdfplumber

import config

log = logging.getLogger(__name__)

INDEX_URL = "https://www.goochlandva.us/Archive.aspx?AMID=60"
BASE_URL = "https://www.goochlandva.us"
TARGET_ZIPS = config.GOOCHLAND_ZIPS

# CivicPlus WAF blocks non-browser user agents
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# City → ZIP for when the PDF lists city names without ZIP codes.
# Only target-territory cities are mapped; everything else stays
# un-zipped and gets dropped downstream.
CITY_ZIP_MAP = {
    "manakin sabot": "23103",
    "manakin-sabot": "23103",
    "manakin": "23103",   # OCR often drops/garbles "Sabot"
    "oilville": "23129",
}

RESIDENTIAL_KEYWORDS = [
    "residential", "single family", "dwelling", "sfd", "addition",
    "renovation", "remodel", "pool", "deck", "porch", "garage",
    "accessory", "basement", "kitchen", "bath",
]


def fetch_permits(since_days: int = 14) -> list[dict]:
    """Fetch permits from the latest Goochland monthly Permits Issued PDFs."""
    items = _find_report_items()
    if not items:
        log.warning("Goochland: no Permits Issued reports found in Archive Center")
        return []

    records: list[dict] = []
    # Latest two reports cover the month boundary on weekly runs;
    # address-level dedup downstream makes re-reads safe.
    for url, label in items[:2]:
        log.info("Goochland: downloading %s (%s)", url, label)
        try:
            r = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=60)
            r.raise_for_status()
        except Exception as e:
            log.error("Goochland: PDF download failed for %s: %s", url, e)
            continue
        if not r.content[:5].startswith(b"%PDF"):
            log.warning("Goochland: %s did not return a PDF (got %s)",
                        url, r.headers.get("content-type"))
            continue
        parsed = _parse_pdf(r.content)
        log.info("Goochland: extracted %d records from %s", len(parsed), label)
        records.extend(parsed)

    filtered = [r for r in records if _is_residential(r) and _assign_zip(r)]
    log.info("Goochland: %d residential permits in target ZIPs (of %d total)",
             len(filtered), len(records))
    return filtered


def _find_report_items() -> list[tuple[str, str]]:
    """
    Return [(pdf_url, label)] for Permits Issued reports, newest first.
    CivicPlus Archive.aspx lists items as links like:
        <a href="/Archive.aspx?ADID=123">Permits Issued - November 2025</a>
    The file itself is served from /ArchiveCenter/ViewFile/Item/{ADID}.
    """
    try:
        r = httpx.get(INDEX_URL, headers=HEADERS, follow_redirects=True, timeout=30)
        r.raise_for_status()
    except Exception as e:
        log.error("Goochland: could not fetch Archive Center listing: %s", e)
        return []

    return _extract_report_items(r.text)


def _extract_report_items(html: str) -> list[tuple[str, str]]:
    items: list[tuple[int, str, str]] = []

    # Match ADID= or ViewFile/Item/ links in any quoting style, tolerating
    # &amp;-encoded query strings and nested tags inside the anchor text.
    for m in re.finditer(
        r"""<a[^>]+href\s*=\s*["']([^"']*(?:ADID=|ViewFile/Item/)(\d+)[^"']*)["'][^>]*>(.*?)</a>""",
        html, re.IGNORECASE | re.DOTALL,
    ):
        adid = int(m.group(2))
        label = re.sub(r"<[^>]+>", "", m.group(3)).strip()
        items.append((adid, f"{BASE_URL}/ArchiveCenter/ViewFile/Item/{adid}", label))

    # Keep permit reports only (defensive: AMID=60 should be all permits,
    # but labels can vary — accept anything mentioning permit)
    seen: set[int] = set()
    unique: list[tuple[int, str, str]] = []
    for adid, url, label in items:
        if adid in seen:
            continue
        seen.add(adid)
        if "permit" in label.lower() or not label:
            unique.append((adid, url, label))

    # Highest ADID = newest upload
    unique.sort(key=lambda t: t[0], reverse=True)
    return [(url, label or f"item {adid}") for adid, url, label in unique]


def _parse_pdf(content: bytes) -> list[dict]:
    """Extract permit records — tables first, text lines, then OCR fallback."""
    records: list[dict] = []
    full_text = ""

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table and len(table) > 1:
                records.extend(_parse_table_rows(table))
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    if not records and not full_text.strip():
        # Goochland reports are scanned images with no text layer — OCR them.
        # The monthly PDF is a stack of scanned permit APPLICATION FORMS
        # (handwritten), so parse label-anchored form fields per page.
        pages = _ocr_pdf_pages(content)
        if any(re.search(r"site\s*address", p, re.IGNORECASE) for p in pages):
            return _parse_application_forms(pages)
        full_text = "\n".join(pages)

    if not records and full_text:
        records = _parse_text_lines(full_text)

    return records


def _ocr_pdf_pages(content: bytes) -> list[str]:
    """
    Render each page with pypdfium2 (a pdfplumber dependency) and OCR
    with tesseract. Requires the tesseract-ocr binary + pytesseract
    (installed in the GitHub Actions workflows).
    """
    try:
        import pypdfium2 as pdfium
        import pytesseract
    except ImportError as e:
        log.error("Goochland: OCR unavailable (%s) — scanned PDF skipped", e)
        return []

    pages = []
    try:
        pdf = pdfium.PdfDocument(io.BytesIO(content))
        for page in pdf:
            bitmap = page.render(scale=300 / 72)  # 300 DPI
            image = bitmap.to_pil()
            # PSM 6: assume a uniform block of text
            pages.append(pytesseract.image_to_string(image, config="--psm 6"))
        pdf.close()
    except Exception as e:
        log.error("Goochland: OCR failed: %s", e)
        return pages

    log.info("Goochland: OCR extracted %d pages (%d chars)",
             len(pages), sum(len(p) for p in pages))
    return pages


def _ocr_pdf(content: bytes) -> str:
    return "\n".join(_ocr_pdf_pages(content))


def _parse_application_forms(pages: list[str]) -> list[dict]:
    """
    Parse OCR'd scanned permit application forms (one form per 1-2 pages).
    Handwritten fields OCR poorly, so extract only the load-bearing ones:
    site address (+ ZIP/city) and scope of work. Owner names are left
    empty on purpose — garbled OCR names must not end up on postcards;
    the postcard falls back to "Homeowner" and enrichment fills the rest.
    """
    records: list[dict] = []
    seen: set[str] = set()

    for page in pages:
        if not re.search(r"site\s*address", page, re.IGNORECASE):
            continue
        lines = [ln.strip() for ln in page.splitlines()]

        # Locate the Site Address label and scan the next few lines
        addr = ""
        zip_code = ""
        for i, ln in enumerate(lines):
            if not re.search(r"site\s*address", ln, re.IGNORECASE):
                continue
            for cand in lines[i + 1:i + 4]:
                m = re.search(r"(\d{1,6}\s+[A-Za-z].*)", cand)
                if m:
                    addr = m.group(1).strip()
                    zm = re.search(r"\b(2[23]\d{3})\b", cand)
                    if zm:
                        zip_code = zm.group(1)
                    break
            break
        if not addr:
            continue

        # Trim trailing OCR junk after the ZIP (if present)
        if zip_code:
            addr = addr[:addr.find(zip_code) + 5]

        # Scope of work — first substantive line after the label
        scope = ""
        for i, ln in enumerate(lines):
            if re.search(r"scope\s*of\s*work", ln, re.IGNORECASE):
                inline = re.sub(r".*scope\s*of\s*work\s*:?", "", ln, flags=re.IGNORECASE).strip()
                if len(inline) > 8:
                    scope = inline
                    break
                for cand in lines[i + 1:i + 4]:
                    cleaned = re.sub(r"^[^A-Za-z]+", "", cand).strip()
                    if len(cleaned) > 8:
                        scope = cleaned
                        break
                break

        page_lower = page.lower()
        is_commercial = "commercial building permit" in page_lower
        permit_type = "Commercial Building" if is_commercial else "Residential Building"

        # The street portion (before city/state) is the dedup + insert key
        street = re.split(r",", addr)[0].strip()
        street, city = _split_city_from_street(street)
        key = street.lower()
        if key in seen:
            continue
        seen.add(key)

        records.append({
            "source": "Goochland",
            "permit_number": "",
            "permit_type": permit_type,
            "property_address": street,
            "property_city": city or "Goochland",
            "property_state": "VA",
            "property_zip": zip_code,
            "description": scope or addr,  # keep full addr for city inference
            "file_date": "",
            "job_value_dollars": 0,
            "owner_name": "",   # handwriting OCR too unreliable for mail
            "contractor_name": "",
        })

    log.info("Goochland: parsed %d application forms", len(records))
    return records


def _parse_table_rows(table: list[list]) -> list[dict]:
    """
    Map table rows to permit dicts using header-based column detection.
    Column names are matched loosely since the exact layout is unknown
    until we see a real report (tune via the Scraper Debug workflow).
    """
    header = [(c or "").strip().lower() for c in table[0]]

    def col(*keywords) -> int | None:
        for i, h in enumerate(header):
            if any(k in h for k in keywords):
                return i
        return None

    c_num   = col("permit", "number", "case")
    c_type  = col("type", "class", "work")
    c_addr  = col("address", "location", "site")
    c_desc  = col("description", "project", "scope")
    c_owner = col("owner", "applicant", "name")
    c_contr = col("contractor")
    c_date  = col("issue", "date")
    c_value = col("value", "valuation", "cost")

    def cell(row: list, idx: int | None) -> str:
        if idx is None or idx >= len(row):
            return ""
        return (row[idx] or "").replace("\n", " ").strip()

    records = []
    for row in table[1:]:
        if not any(row):
            continue
        address = cell(row, c_addr)
        if not address:
            continue
        records.append(_make_record(
            permit_number=cell(row, c_num),
            permit_type=cell(row, c_type),
            address=address,
            description=cell(row, c_desc),
            owner_name=cell(row, c_owner),
            contractor_name=cell(row, c_contr),
            issued_date=cell(row, c_date),
            value_str=cell(row, c_value),
        ))
    return records


def _parse_text_lines(text: str) -> list[dict]:
    """
    Fallback: parse plain-text lines that contain a date and a street
    address. Handles layouts like:
        B-2026-0123  1/15/2026  RESIDENTIAL  123 RIVER RD MANAKIN SABOT  $250,000
    """
    records = []
    line_pattern = re.compile(
        r"^(?P<num>[A-Z]{1,4}[-\s]?\d{2,4}[-\s]?\d{3,6})?\s*"
        r"(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+"
        r"(?P<rest>.+)$"
    )
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < 15:
            continue
        m = line_pattern.match(line)
        if not m:
            continue
        rest = m.group("rest").strip()
        addr_m = re.search(r"\b(\d{1,6}\s+[A-Z][A-Za-z0-9 .'-]+)", rest)
        if not addr_m:
            continue
        val_m = re.search(r"\$\s?([\d,]+(?:\.\d{2})?)", rest)
        value_str = val_m.group(1) if val_m else ""
        records.append(_make_record(
            permit_number=(m.group("num") or "").strip(),
            permit_type=rest[:addr_m.start()].strip(),
            address=addr_m.group(1).strip(),
            description=rest,
            owner_name="",
            contractor_name="",
            issued_date=m.group("date"),
            value_str=value_str,
        ))
    return records


def _make_record(permit_number, permit_type, address, description,
                 owner_name, contractor_name, issued_date, value_str) -> dict:
    try:
        value = int(float(value_str.replace("$", "").replace(",", ""))) if value_str else 0
    except ValueError:
        value = 0
    return {
        "source": "Goochland",
        "permit_number": permit_number,
        "permit_type": permit_type or "Residential Building",
        "property_address": address,
        "property_city": "Goochland",
        "property_state": "VA",
        "property_zip": _extract_zip(f"{address} {description}"),
        "description": description,
        "file_date": _normalize_date(issued_date),
        "job_value_dollars": value,
        "owner_name": owner_name,
        "contractor_name": contractor_name,
    }


# Goochland County post-office city names, longest first so
# "manakin sabot" wins over "manakin"
GOOCHLAND_CITIES = [
    "manakin sabot", "manakin-sabot", "gum spring", "sandy hook",
    "kents store", "hadensville", "goochland", "oilville", "maidens",
    "crozier", "columbia", "manakin",
]


def _split_city_from_street(street: str) -> tuple[str, str]:
    """Strip a trailing Goochland city name off an OCR'd street line."""
    lowered = street.lower()
    for city in GOOCHLAND_CITIES:
        idx = lowered.rfind(city)
        if idx > 0 and idx + len(city) >= len(lowered) - 3:
            return street[:idx].strip(" ,.-"), street[idx:idx + len(city)].title()
    return street, ""


def _is_residential(record: dict) -> bool:
    blob = f"{record.get('permit_type','')} {record.get('description','')}".lower()
    if "commercial" in blob:
        return False
    return any(k in blob for k in RESIDENTIAL_KEYWORDS)


def _assign_zip(record: dict) -> bool:
    """Ensure the record has a target-territory ZIP; infer from city names."""
    z = record.get("property_zip", "")
    if z:
        return z in TARGET_ZIPS
    blob = (f"{record.get('property_address','')} {record.get('property_city','')} "
            f"{record.get('description','')}").lower()
    for city, city_zip in CITY_ZIP_MAP.items():
        if city in blob:
            record["property_zip"] = city_zip
            record["property_city"] = city.replace("-", " ").title()
            return True
    return False


def _extract_zip(text: str) -> str:
    m = re.search(r"\b(23\d{3})\b", text)
    return m.group(1) if m else ""


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
    """Dump the archive listing, raw text of the latest PDF, and parsed records."""
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
        # Also show any occurrences of 'permit' with context
        for m in list(re.finditer(r"permit", r.text, re.IGNORECASE))[:10]:
            s = max(0, m.start() - 120)
            print(f"  CONTEXT: {' '.join(r.text[s:m.end()+120].split())}")
        return

    url, label = items[0]
    print(f"\n=== Downloading latest: {label} ===")
    r = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=60)
    print(f"HTTP {r.status_code}  content-type={r.headers.get('content-type')}  bytes={len(r.content)}")
    if not r.content[:5].startswith(b"%PDF"):
        print("Not a PDF — first 500 bytes:")
        print(r.content[:500])
        return

    has_text = False
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        print(f"\n=== PDF has {len(pdf.pages)} pages ===")
        for i, page in enumerate(pdf.pages[:3]):
            print(f"\n--- Page {i+1} raw text ---")
            text = page.extract_text()
            if text:
                has_text = True
            print(text or "(no text extracted)")
            table = page.extract_table()
            if table:
                print(f"\n--- Page {i+1} table ({len(table)} rows) ---")
                for row in table[:8]:
                    print(f"  {row}")

    if not has_text:
        print("\n=== No text layer — OCR output (first 2 pages worth) ===")
        ocr_text = _ocr_pdf(r.content)
        print(ocr_text[:6000] or "(OCR produced nothing)")

    records = _parse_pdf(r.content)
    print(f"\n=== Parsed {len(records)} records ===")
    for rec in records[:10]:
        print(f"  {rec}")
    kept = [rec for rec in records if _is_residential(rec) and _assign_zip(rec)]
    print(f"\n=== {len(kept)} residential records in target ZIPs ===")
    for rec in kept[:10]:
        print(f"  {rec}")


if __name__ == "__main__":
    _debug()
