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
            page.wait_for_load_state("networkidle", timeout=30000)

            # Module dropdown: pick Permit (CSS renders <select id="SearchModule">)
            module_select = page.query_selector("#SearchModule") or \
                            page.query_selector("select[name='SearchModule']")
            if module_select:
                _select_option_by_label(page, module_select, "Permit")
                page.wait_for_timeout(1500)

            # Advanced search reveal (link/button labeled Advanced)
            adv = page.query_selector("a:has-text('Advanced')") or \
                  page.query_selector("button:has-text('Advanced')")
            if adv:
                adv.click()
                page.wait_for_timeout(1000)

            # Issued date range — CSS commonly uses IssuedOnFrom/IssuedOnTo
            filled = False
            for from_sel, to_sel in (
                ("#IssuedOnFrom", "#IssuedOnTo"),
                ("#IssueDateFrom", "#IssueDateTo"),
                ("input[name='IssuedOnFrom']", "input[name='IssuedOnTo']"),
            ):
                if page.query_selector(from_sel) and page.query_selector(to_sel):
                    page.fill(from_sel, date_from)
                    page.fill(to_sel, date_to)
                    filled = True
                    break
            if not filled:
                log.warning("EnerGov: date-range inputs not found on %s", base)

            # Search button
            btn = page.query_selector("#button-Search") or \
                  page.query_selector("button:has-text('Search')")
            if not btn:
                log.error("EnerGov: search button not found on %s", base)
                return None
            btn.click()
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_timeout(2000)

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


def _extract_results(page) -> list[dict]:
    """
    Result cards in CSS render as repeated blocks with labeled fields.
    Extract number / type / address / date / description generically:
    each card contains a link to permit detail (#/permit/<guid>).
    """
    records = []
    cards = page.query_selector_all("[name='label-SearchResultModel'], .search-result, "
                                    "div[id^='entityRecordDiv']")
    if not cards:
        # Fallback: any element containing a permit detail link
        cards = page.query_selector_all("div:has(> a[href*='#/permit/'])")

    for card in cards:
        text = card.inner_text() or ""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            continue
        rec = {"number": "", "type": "", "address": "", "date": "", "description": ""}
        link = card.query_selector("a[href*='#/permit/']")
        if link:
            rec["number"] = (link.inner_text() or "").strip()
        for i, ln in enumerate(lines):
            low = ln.lower()
            if low.startswith("type") and i + 1 <= len(lines):
                rec["type"] = ln.split(":", 1)[-1].strip() or (lines[i + 1] if i + 1 < len(lines) else "")
            elif low.startswith("address"):
                rec["address"] = ln.split(":", 1)[-1].strip() or (lines[i + 1] if i + 1 < len(lines) else "")
            elif "issued" in low and re.search(r"\d{1,2}/\d{1,2}/\d{4}", ln):
                m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", ln)
                rec["date"] = _normalize_date(m.group(1))
            elif low.startswith("description"):
                rec["description"] = ln.split(":", 1)[-1].strip()
        if not rec["address"]:
            # Heuristic: first line with digits + letters + VA/zip
            for ln in lines:
                if re.search(r"\d{1,6}\s+[A-Za-z]", ln) and ("VA" in ln.upper() or re.search(r"\b22\d{3}\b", ln)):
                    rec["address"] = ln
                    break
        if rec["number"] or rec["address"]:
            records.append(rec)
    return records


def _parse_address(raw: str) -> dict:
    m = re.match(r"^(.+?),?\s*([A-Za-z .]+?)?,?\s*VA[,\s]+(\d{5})", raw or "", re.IGNORECASE)
    if m:
        return {"street": m.group(1).strip(" ,"), "city": (m.group(2) or "").strip(" ,"),
                "zip": m.group(3)}
    zm = re.search(r"\b(\d{5})\b", raw or "")
    return {"street": re.split(r",", raw or "")[0].strip(),
            "city": "", "zip": zm.group(1) if zm else ""}


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

            # Dump the first result card's HTML for selector design
            for probe in ("[name='label-SearchResultModel']", ".search-result",
                          "div[id^='entityRecordDiv']", "app-search-result",
                          "div:has(> a[href*='permit'])"):
                cards = page.query_selector_all(probe)
                if cards:
                    print(f"result container matched: {probe} x{len(cards)}")
                    html = cards[0].evaluate("e => e.outerHTML")
                    print(html[:2500])
                    break
            else:
                body = page.inner_text("body") or ""
                idx = body.lower().find("found")
                print("no card selector matched; body snippet:")
                print(body[max(0, idx-200):idx+1200])
        except Exception as e:
            print(f"  DOM dump failed: {e}")
        finally:
            browser.close()


def _debug():
    logging.basicConfig(level=logging.INFO)
    for name, t in TENANTS.items():
        _dump_dom(name, t["base"])


if __name__ == "__main__":
    _debug()
