"""
spotsylvania.py — Spotsylvania County permit scraper.

Source: Monthly "Permits Issued" PDFs in the county's CivicPlus Archive
Center (AMID=47), linked from /763/Monthly-Permit-Reports.

Layout (confirmed via Scraper Debug run against the June 2026 report):
each permit is a 4-line block across 4 columns —

    col 1            col 2               col 3              col 4
    PERMIT NUMBER    review track        APPLICANT NAME     ADDRESS
    ISSUED DATE      PERMIT SUBTYPE      OWNER NAME         PARCEL NUMBER
    APPLIED DATE     STATUS              CONTRACTOR NAME    SUBDIVISION
    DESCRIPTION                                             LOT BLOCK & TRACT

Addresses carry NO ZIP code and the county spans many ZIPs, so ZIPs are
resolved through the free US Census geocoder for records that pass a
project-keyword pre-filter (bounds geocoding volume).

ZIPs: 22407, 22553. Cadence: monthly.

Debug: python -m pipeline.scrapers.spotsylvania  (via Scraper Debug workflow)
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

CENSUS_GEOCODER = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
GEOCODE_CAP = 80  # per run — bounds latency; log when hit

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
PERMIT_NUM_RE = re.compile(r"^[A-Z]{2,4}\d{2}-\d{3,6}$")
PAGE_NOISE = ("permits issued", "spotsylvania county", "date range", "printed:",
              "permit number", "issued date", "applied date", "description", "details")

# Pre-filter before geocoding: worth a lookup only if the scope suggests a
# real project. Superset of QUALIFYING_TAGS plus new-dwelling phrasing.
INTEREST_KEYWORDS = list(config.QUALIFYING_TAGS) + [
    "dwelling", "single family", "sfd", "new construction", "garage",
]


def fetch_permits(since_days: int = 14) -> list[dict]:
    items = _find_report_items()
    if not items:
        log.warning("Spotsylvania: no monthly permit reports found in Archive Center")
        return []

    records: list[dict] = []
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
        log.info("Spotsylvania: extracted %d permit blocks from %s", len(parsed), label)
        records.extend(parsed)

    interesting = [r for r in records if _passes_prefilter(r)]
    log.info("Spotsylvania: %d of %d pass project pre-filter; geocoding for ZIPs...",
             len(interesting), len(records))

    kept = []
    geocoded = 0
    for rec in interesting:
        if geocoded >= GEOCODE_CAP:
            log.warning("Spotsylvania: geocode cap (%d) reached — %d records skipped",
                        GEOCODE_CAP, len(interesting) - geocoded)
            break
        zip_code, city = _geocode_zip(rec["property_address"])
        geocoded += 1
        if zip_code in TARGET_ZIPS:
            rec["property_zip"] = zip_code
            if city:
                rec["property_city"] = city
            kept.append(rec)

    log.info("Spotsylvania: %d permits in target ZIPs", len(kept))
    return kept


# ── Archive Center listing ────────────────────────────────────────────────────

def _find_report_items() -> list[tuple[str, str]]:
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
        if "total" in low or "dwelling" in low:
            continue
        if "permit" in low or not label:
            unique.append((adid, url, label))

    unique.sort(key=lambda t: t[0], reverse=True)
    return [(url, label or f"item {adid}") for adid, url, label in unique]


# ── PDF block parser ──────────────────────────────────────────────────────────

def _parse_pdf(content: bytes) -> list[dict]:
    records: list[dict] = []
    col_bounds: list[float] | None = None

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue
            if col_bounds is None:
                col_bounds = _find_column_bounds(words)
            if col_bounds is None:
                continue
            lines = _group_lines(words, col_bounds)
            records.extend(_parse_blocks(lines))

    return records


def _find_column_bounds(words: list[dict]) -> list[float] | None:
    """
    Locate the header row (PERMIT NUMBER | PERMIT TYPE | APPLICANT NAME |
    ADDRESS) and return the x-start of each of the 4 columns.
    """
    # Group header candidates by line
    by_top: dict[int, list[dict]] = {}
    for w in words:
        by_top.setdefault(int(w["top"] // 3), []).append(w)

    for grp in by_top.values():
        texts = [w["text"].upper() for w in grp]
        if "APPLICANT" in texts and "ADDRESS" in texts and texts.count("PERMIT") >= 2:
            grp_sorted = sorted(grp, key=lambda w: w["x0"])
            permit_xs = [w["x0"] for w in grp_sorted if w["text"].upper() == "PERMIT"]
            applicant_x = next(w["x0"] for w in grp_sorted if w["text"].upper() == "APPLICANT")
            address_x = next(w["x0"] for w in grp_sorted if w["text"].upper() == "ADDRESS")
            if len(permit_xs) >= 2:
                return [permit_xs[0], permit_xs[1], applicant_x, address_x]
    return None


def _group_lines(words: list[dict], col_bounds: list[float]) -> list[list[str]]:
    """Group words into visual lines, then bucket each line's words into 4 columns."""
    by_top: dict[int, list[dict]] = {}
    for w in words:
        by_top.setdefault(int(w["top"] // 3), []).append(w)

    lines = []
    for key in sorted(by_top):
        cols = ["", "", "", ""]
        for w in sorted(by_top[key], key=lambda w: w["x0"]):
            idx = 0
            for i, bound in enumerate(col_bounds):
                if w["x0"] >= bound - 4:
                    idx = i
            cols[idx] = (cols[idx] + " " + w["text"]).strip()
        lines.append(cols)
    return lines


def _parse_blocks(lines: list[list[str]]) -> list[dict]:
    records = []
    block: dict | None = None

    def flush():
        nonlocal block
        if block and block.get("address"):
            records.append(_make_record(block))
        block = None

    for cols in lines:
        c0, c1, c2, c3 = cols
        low0 = c0.lower()
        if any(low0.startswith(n) for n in PAGE_NOISE):
            continue

        if PERMIT_NUM_RE.match(c0):
            flush()
            block = {"number": c0, "applicant": c2, "address": c3,
                     "dates": [], "subtype": "", "status": "",
                     "owner": "", "contractor": "", "desc": []}
            continue

        if block is None:
            continue

        if DATE_RE.match(c0):
            block["dates"].append(c0)
            if len(block["dates"]) == 1:      # issued-date line
                block["subtype"] = c1
                block["owner"] = c2
            else:                              # applied-date line
                block["status"] = c1
                block["contractor"] = c2
            continue

        # Continuation / description lines
        if c2 and not c0 and not c1:
            # wrapped contact name (e.g. "LLC" under the contractor)
            if len(block["dates"]) >= 2:
                block["contractor"] = f'{block["contractor"]} {c2}'.strip()
            else:
                block["owner"] = f'{block["owner"]} {c2}'.strip()
            continue
        if c0:
            block["desc"].append(c0)

    flush()
    return records


def _make_record(block: dict) -> dict:
    owner_raw = (block["owner"] or "").strip()
    # County suffixes owner names with "OR" (co-owner notation) — drop it
    owner_raw = re.sub(r"\s+OR$", "", owner_raw)
    owner_name = ""
    if owner_raw:
        upper = f" {owner_raw.upper()} "
        if not any(pat in upper for pat in config.COMPANY_PATTERNS):
            owner_name = owner_raw.title()

    subtype = block["subtype"] or ""
    description = " ".join([subtype] + block["desc"]).strip()

    return {
        "source": "Spotsylvania",
        "permit_number": block["number"],
        "permit_type": subtype.title() or "Residential Building",
        "property_address": block["address"].strip(),
        "property_city": "Fredericksburg",
        "property_state": "VA",
        "property_zip": "",
        "description": description,
        "file_date": _normalize_date(block["dates"][0] if block["dates"] else ""),
        "job_value_dollars": 0,
        "owner_name": owner_name,
        "contractor_name": (block["contractor"] or "").title(),
        "_status": block["status"],
    }


def _passes_prefilter(record: dict) -> bool:
    if not record["permit_number"].upper().startswith("RES"):
        return False
    status = (record.get("_status") or "").upper()
    if status and "ISSUED" not in status:
        return False
    text = f'{record["permit_type"]} {record["description"]}'.lower()
    if any(kw in text for kw in config.MAINTENANCE_KEYWORDS):
        return False
    return any(kw in text for kw in INTEREST_KEYWORDS)


# ── ZIP resolution via US Census geocoder ─────────────────────────────────────

def _geocode_zip(street: str) -> tuple[str, str]:
    """Return (zip, city) for a Spotsylvania County street address, or ('', '')."""
    for city in ("FREDERICKSBURG", "SPOTSYLVANIA"):
        try:
            r = httpx.get(CENSUS_GEOCODER, params={
                "address": f"{street}, {city}, VA",
                "benchmark": "Public_AR_Current",
                "format": "json",
            }, timeout=15)
            r.raise_for_status()
            matches = r.json().get("result", {}).get("addressMatches", [])
            if matches:
                matched = matches[0].get("matchedAddress", "")
                zm = re.search(r"\b(\d{5})\b", matched)
                cm = re.search(r",\s*([A-Z ]+),\s*VA", matched)
                return (zm.group(1) if zm else "",
                        cm.group(1).title().strip() if cm else "")
        except Exception as e:
            log.debug("Spotsylvania: geocode failed for %s (%s): %s", street, city, e)
    return "", ""


def _normalize_date(val: str) -> str:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", val or "")
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return val or ""


# ── Debug entrypoint ──────────────────────────────────────────────────────────

def _debug():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")
    items = _find_report_items()
    print(f"=== {len(items)} Archive Center items ===")
    for url, label in items[:5]:
        print(f"  {label}  ->  {url}")
    if not items:
        return

    url, label = items[0]
    print(f"\n=== Downloading latest: {label} ===")
    r = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=60)
    print(f"HTTP {r.status_code}  bytes={len(r.content)}")

    records = _parse_pdf(r.content)
    print(f"\n=== Parsed {len(records)} permit blocks (first 6) ===")
    for rec in records[:6]:
        print(f"  {rec}")

    interesting = [rec for rec in records if _passes_prefilter(rec)]
    print(f"\n=== {len(interesting)} pass project pre-filter (first 10) ===")
    for rec in interesting[:10]:
        print(f'  {rec["permit_number"]} | {rec["property_address"][:30]:30} | '
              f'{rec["description"][:60]}')

    print("\n=== Geocoding first 5 interesting records ===")
    for rec in interesting[:5]:
        z, city = _geocode_zip(rec["property_address"])
        mark = "TARGET" if z in TARGET_ZIPS else ""
        print(f'  {rec["property_address"][:35]:35} -> zip={z or "?"} city={city or "?"} {mark}')


if __name__ == "__main__":
    _debug()
