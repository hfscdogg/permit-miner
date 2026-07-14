"""
energov.py — Shared Playwright driver for Tyler EnerGov Citizen Self
Service portals (Albemarle County, City of Fredericksburg).

The CSS portals are Angular SPAs. Anonymous search is confirmed
reachable (probe run 2026-07-14: both portals serve the SPA anonymously
and expose api/energov/search/search). The exact JSON payload is
version-specific, so we drive the UI with Playwright instead — same
approach as the Chesterfield/Accela scraper.

Flow: open #/search → module = Permit → advanced search → issued-date
range → collect result cards across pages.

Debug (dumps the live DOM's selects/inputs/buttons so selectors can be
pinned):  python -m pipeline.scrapers.energov
"""
import logging
import re
from datetime import date, timedelta

log = logging.getLogger(__name__)

TENANTS = {
    "Albemarle": {
        "base": "https://albemarlecountyva-energovweb.tylerhost.net/apps/selfservice",
        "default_city": "Charlottesville",
    },
    "Fredericksburg": {
        "base": "https://selfservice.fredericksburgva.gov/energov_prod/selfservice",
        "default_city": "Fredericksburg",
    },
    "James City": {
        "base": "https://jamescitycountyva-energovweb.tylerhost.net/apps/selfservice",
        "default_city": "Williamsburg",
    },
}

MAX_PAGES = 15


def fetch_permits_for(source: str, target_zips: set, since_days: int = 14) -> list[dict]:
    """Fetch recent permits from one EnerGov tenant, filtered to target ZIPs."""
    tenant = TENANTS[source]
    date_from = (date.today() - timedelta(days=since_days)).strftime("%m/%d/%Y")
    date_to = date.today().strftime("%m/%d/%Y")
    log.info("%s (EnerGov): fetching permits %s to %s", source, date_from, date_to)

    rows = _scrape(tenant["base"], date_from, date_to)
    if rows is None:
        log.warning("%s (EnerGov): scrape failed, returning empty list", source)
        return []

    records = []
    for row in rows:
        status = (row.get("status") or "").lower()
        if any(bad in status for bad in ("denied", "expired", "void", "withdrawn")):
            continue
        parsed = _parse_address(row.get("address", ""))
        if parsed["zip"] not in target_zips:
            continue
        records.append({
            "source": source,
            "permit_number": row.get("number", ""),
            "permit_type": row.get("type", ""),
            "property_address": parsed["street"],
            "property_city": parsed["city"] or tenant["default_city"],
            "property_state": "VA",
            "property_zip": parsed["zip"],
            "description": row.get("description", ""),
            "file_date": row.get("date", ""),
            "job_value_dollars": 0,
            "owner_name": "",
            "contractor_name": "",
        })

    log.info("%s (EnerGov): %d permits total, %d in target ZIPs",
             source, len(rows), len(records))
    return records


def _scrape(base: str, date_from: str, date_to: str) -> list[dict] | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("Playwright not installed — EnerGov scrape skipped")
        return None

    results: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(f"{base}#/search", timeout=45000)
            # Element existence != Angular bootstrapped: give the SPA time
            # to bind handlers, or the module change never registers and
            # #button-Advanced stays ng-hidden.
            page.wait_for_selector("#SearchModule", timeout=45000)
            page.wait_for_timeout(3000)

            # Playwright's select_option fires proper input/change events
            page.select_option("#SearchModule", label="Permit")
            page.wait_for_timeout(1000)

            try:
                page.wait_for_selector("#button-Advanced:visible", timeout=8000)
                page.click("#button-Advanced")
            except Exception:
                # ng-show hasn't flipped — Angular still honors programmatic clicks
                page.eval_on_selector("#button-Advanced", "el => el.click()")

            page.wait_for_selector("#IssueDateFrom", timeout=15000)
            page.fill("#IssueDateFrom", date_from)
            page.fill("#IssueDateTo", date_to)

            page.click("#button-Search")
            page.wait_for_selector("div[id^='entityRecordDiv']", timeout=30000)
            page.wait_for_timeout(1500)

            # Bump page size to 100 to minimize pagination
            size_sel = page.query_selector("#pageSizeList")
            if size_sel:
                try:
                    size_sel.select_option(value="100")
                    page.wait_for_timeout(2500)
                except Exception:
                    pass

            for page_num in range(1, MAX_PAGES + 1):
                batch = _extract_results(page)
                results.extend(batch)
                log.debug("EnerGov %s: page %d — %d results", base, page_num, len(batch))
                nxt = page.query_selector("a[aria-label='Next page']:not(.disabled)") or \
                      page.query_selector("li:not(.disabled) > a:has-text('»')")
                if not nxt or not batch:
                    break
                nxt.click()
                page.wait_for_timeout(2500)

        except Exception as e:
            log.error("EnerGov scrape failed for %s: %s", base, e)
            return results or None
        finally:
            browser.close()

    return results


def _select_option_by_label(page, select_el, label: str):
    for opt in select_el.query_selector_all("option"):
        if label.lower() in (opt.inner_text() or "").lower():
            select_el.select_option(value=opt.get_attribute("value"))
            return


# Card lines are label-prefixed (confirmed via 2026-07-14 debug run):
#   Permit Number OTH-2026-00007 / Type Building - ... / Issued Date 06/30/2026
#   Status Issued / Address 6550 ROSELAND FARM CROZET VA 22932 / Description ...
CARD_FIELDS = [
    ("Permit Number", "number"),
    ("Issued Date", "date"),        # before bare "Type"/"Status" checks
    ("Type", "type"),
    ("Status", "status"),
    ("Address", "address"),
    ("Description", "description"),
]


def _extract_results(page) -> list[dict]:
    records = []
    for card in page.query_selector_all("div[id^='entityRecordDiv']"):
        text = card.inner_text() or ""
        rec = {"number": "", "type": "", "address": "", "date": "",
               "status": "", "description": ""}
        for ln in text.splitlines():
            ln = ln.strip()
            for label, key in CARD_FIELDS:
                if ln.startswith(label + " "):
                    val = ln[len(label):].strip()
                    if key == "date":
                        rec[key] = _normalize_date(val)
                    elif not rec[key]:
                        rec[key] = val
                    break
        if rec["number"] or rec["address"]:
            records.append(rec)
    return records


# City names seen in these tenants' addresses ("STREET CITY VA ZIP", no commas)
KNOWN_CITIES = [
    "CHARLOTTESVILLE", "CROZET", "KESWICK", "EARLYSVILLE", "SCOTTSVILLE",
    "NORTH GARDEN", "FREE UNION", "WHITE HALL", "AFTON", "BARBOURSVILLE",
    "PALMYRA", "TROY", "FREDERICKSBURG",
    "WILLIAMSBURG", "TOANO", "NORGE", "LANEXA",
]


def _parse_address(raw: str) -> dict:
    raw = (raw or "").strip()
    m = re.match(r"^(.*?)\s+VA\s+(\d{5})(?:-\d{4})?$", raw, re.IGNORECASE)
    if not m:
        zm = re.search(r"\b(\d{5})\b", raw)
        return {"street": re.split(r",", raw)[0].strip(),
                "city": "", "zip": zm.group(1) if zm else ""}
    head, zip_code = m.group(1).strip(" ,"), m.group(2)
    street, city = head, ""
    upper = head.upper()
    for c in KNOWN_CITIES:
        if upper.endswith(" " + c) or upper.endswith("," + c):
            street = head[: len(head) - len(c)].strip(" ,")
            city = c.title()
            break
    return {"street": street, "city": city, "zip": zip_code}


def _normalize_date(val: str) -> str:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", val or "")
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return val or ""


# ── Debug entrypoint ──────────────────────────────────────────────────────────

def _dump_inputs(page, note: str):
    print(f"--- <input>/<select> after {note} ---")
    for inp in page.query_selector_all("input"):
        iid = inp.get_attribute("id") or ""
        if re.search(r"date|issue|appl|final|from|to", iid, re.IGNORECASE):
            print(f"  input id={iid} name={inp.get_attribute('name')} "
                  f"type={inp.get_attribute('type')} placeholder={inp.get_attribute('placeholder')}")
    for sel in page.query_selector_all("select"):
        sid = sel.get_attribute("id") or ""
        if re.search(r"type|status|workclass", sid, re.IGNORECASE):
            opts = [(o.get_attribute("value"), (o.inner_text() or "").strip())
                    for o in sel.query_selector_all("option")]
            print(f"  select id={sid} options={opts[:10]}")


def _dump_dom(name: str, base: str):
    from playwright.sync_api import sync_playwright
    print(f"\n{'='*70}\n=== {name}: {base}#/search\n{'='*70}")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(f"{base}#/search", timeout=45000)
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_timeout(3000)

            # Step 1: module = Permit
            module_select = page.query_selector("#SearchModule")
            if module_select:
                _select_option_by_label(page, module_select, "Permit")
                page.wait_for_timeout(1500)
                print("module=Permit selected")

            # Step 2: Advanced pane
            adv = page.query_selector("#button-Advanced")
            if adv:
                adv.click()
                page.wait_for_timeout(1500)
                print("Advanced clicked")
            _dump_inputs(page, "module=Permit + Advanced")

            # Step 3: fill issued-date range if fields discovered
            date_from = (date.today() - timedelta(days=14)).strftime("%m/%d/%Y")
            date_to = date.today().strftime("%m/%d/%Y")
            filled = None
            for from_sel, to_sel in (
                ("#IssuedOnFrom", "#IssuedOnTo"),
                ("#IssueDateFrom", "#IssueDateTo"),
                ("#PermitCriteria_IssueDateFrom", "#PermitCriteria_IssueDateTo"),
            ):
                if page.query_selector(from_sel) and page.query_selector(to_sel):
                    page.fill(from_sel, date_from)
                    page.fill(to_sel, date_to)
                    filled = (from_sel, to_sel)
                    break
            print(f"date fields filled: {filled}")

            # Step 4: search and dump result structure
            btn = page.query_selector("#button-Search")
            if btn:
                btn.click()
                page.wait_for_load_state("networkidle", timeout=30000)
                page.wait_for_timeout(3000)
                print("Search clicked")

            links = page.query_selector_all("a[href*='permit']")
            print(f"{len(links)} permit-ish links on page; first 5 hrefs:")
            for a in links[:5]:
                print(f"  {a.get_attribute('href')} :: {(a.inner_text() or '').strip()[:40]}")

            # Dump result cards' TEXT for field-extraction design
            cards = page.query_selector_all("div[id^='entityRecordDiv']")
            print(f"entityRecordDiv cards: {len(cards)}")
            for card in cards[:3]:
                print("--- card inner text ---")
                text = card.inner_text() or ""
                for ln in text.splitlines():
                    if ln.strip():
                        print(f"  | {ln.strip()}")
        except Exception as e:
            print(f"  DOM dump failed: {e}")
        finally:
            browser.close()


def _debug():
    import config
    logging.basicConfig(level=logging.INFO)
    zips = {"Albemarle": config.ALBEMARLE_ZIPS, "Fredericksburg": config.FREDERICKSBURG_ZIPS,
            "James City": config.JAMES_CITY_ZIPS}
    for name in TENANTS:
        print(f"\n{'='*70}\n=== production fetch: {name} (target ZIPs {sorted(zips[name])})\n{'='*70}")
        try:
            records = fetch_permits_for(name, zips[name], since_days=14)
            print(f"{len(records)} records in target ZIPs; first 8:")
            for r in records[:8]:
                print(f"  {r['permit_number']} | {r['permit_type'][:38]:38} | "
                      f"{r['property_address'][:28]:28} | {r['property_zip']} | {r['file_date']}")
                print(f"    desc: {r['description'][:90]}")
        except Exception as e:
            print(f"  FAILED: {e}")
            _dump_dom(name, TENANTS[name]["base"])


if __name__ == "__main__":
    _debug()
