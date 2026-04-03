"""
monday_pull.py — Permit Miner Monday 8AM pipeline (no-Shovels).

1. Read scan events (from WordPress) → mark permits Engaged
2. Read exclusion events (from WordPress) → mark permits Excluded
3. Pull permits from county scrapers
4. Filter by owner type, value, permit type
5. Enrich contacts via Apollo API
6. Insert Queued records in SQLite
7. Write data/permit_registry.json (for WordPress scan lookups)
8. Send Monday preview email with signed one-click Exclude links

Run:  python -m pipeline.monday_pull
Cron: 0 13 * * 1  (8AM ET = 13:00 UTC, Monday)
"""
import json
import logging
import sys
from datetime import date, timedelta

import httpx

import config
import db
from pipeline.mailer import send_email
from pipeline.scrapers import virginia_state, chesterfield, goochland, powhatan, hanover
from pipeline.scrapers.assessor import get_assessed_value

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

CUSTOMER_ID = "livewire"


# ── Owner type detection ───────────────────────────────────────────────────────

def owner_is_individual(owner_name: str) -> bool:
    """Returns True if owner_name does not match any company pattern."""
    if not owner_name:
        return False
    name_upper = owner_name.upper()
    for pattern in config.COMPANY_PATTERNS:
        if pattern.upper() in name_upper:
            return False
    return True


# ── Permit classification ──────────────────────────────────────────────────────

def is_new_construction(permit: dict) -> bool:
    """Returns True if permit type/description matches new construction keywords."""
    text = (
        (permit.get("permit_type") or "") + " " +
        (permit.get("description") or "")
    ).lower()
    return any(kw in text for kw in config.NEW_CONSTRUCTION_KEYWORDS)


def passes_tag_filter(permit: dict) -> bool:
    """Returns True if permit type/description contains at least one qualifying keyword."""
    text = (
        (permit.get("permit_type") or "") + " " +
        (permit.get("description") or "")
    ).lower()
    return any(tag in text for tag in config.QUALIFYING_TAGS)


def passes_value_filter(permit: dict, new_construction: bool) -> bool:
    """
    New construction always passes (vacant land has $0 assessed value).
    Otherwise: assessed >= $500K OR job value >= $75K.
    """
    if new_construction:
        return True
    assessed = permit.get("assessed_value_dollars") or 0
    if assessed >= config.MIN_ASSESSED_VALUE_DOLLARS:
        return True
    job_val = permit.get("job_value_dollars") or 0
    return job_val >= config.MIN_JOB_VALUE_DOLLARS


# ── Apollo contact enrichment ──────────────────────────────────────────────────

def enrich_via_apollo(owner_name: str, city: str = "Richmond", state: str = "VA") -> dict:
    """
    POST to Apollo /v1/people/match — returns phone, email, linkedin if found.
    Returns empty dict on failure or missing key.
    """
    if not config.APOLLO_API_KEY:
        return {}
    if not owner_name or not owner_name.strip():
        return {}

    # Parse name into first/last
    parts = owner_name.strip().split()
    first = parts[0] if parts else ""
    last = " ".join(parts[1:]) if len(parts) > 1 else ""
    if not last:
        return {}

    try:
        r = httpx.post(
            "https://api.apollo.io/v1/people/match",
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
            },
            json={
                "api_key": config.APOLLO_API_KEY,
                "first_name": first,
                "last_name": last,
                "organization_name": None,
                "domain": None,
                "city": city,
                "state": state,
                "country": "US",
                "reveal_personal_emails": True,
                "reveal_phone_number": True,
            },
            timeout=20,
        )
        if r.status_code == 200:
            data = r.json()
            person = data.get("person") or {}
            if not person:
                return {}

            # Phone: prefer mobile, fall back to other numbers
            phone = ""
            for pn in person.get("phone_numbers") or []:
                if pn.get("type") in ("mobile", "direct"):
                    phone = pn.get("raw_number") or pn.get("sanitized_number") or ""
                    break
            if not phone:
                numbers = person.get("phone_numbers") or []
                if numbers:
                    phone = numbers[0].get("raw_number") or numbers[0].get("sanitized_number") or ""

            email = person.get("email") or ""
            # Avoid guessed/work emails — prefer personal if available
            if person.get("personal_emails"):
                email = person["personal_emails"][0]

            return {
                "owner_phone":    phone,
                "owner_email":    email,
                "owner_linkedin": person.get("linkedin_url") or "",
            }
        elif r.status_code == 422:
            # Unprocessable — bad name match, not an error
            return {}
        else:
            log.debug("Apollo match returned %d for %s", r.status_code, owner_name)
            return {}
    except Exception as e:
        log.debug("Apollo enrichment failed for %s: %s", owner_name, e)
        return {}


# ── Scan processing (from WordPress) ──────────────────────────────────────────

SCANS_URL = f"{config.WP_BASE_URL}/wp-content/uploads/permit-miner/scans.json"
EXCLUSIONS_URL = f"{config.WP_BASE_URL}/wp-content/uploads/permit-miner/exclusions.json"


def _fetch_wp_json(url: str) -> list[dict]:
    """Fetch a JSON array from a WordPress uploads URL. Returns [] on failure."""
    try:
        r = httpx.get(url, timeout=15)
        if r.status_code == 404:
            return []
        if r.status_code != 200:
            log.info("Fetch %s returned %d -- skipping.", url, r.status_code)
            return []
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        log.warning("Could not fetch %s: %s", url, e)
        return []


def process_scans():
    """Fetch scan events from WordPress and mark permits as Engaged in DB."""
    scans = _fetch_wp_json(SCANS_URL)
    if not scans:
        log.info("No new scans to process.")
        return

    engaged = 0
    for scan in scans:
        pid = scan.get("pid")
        if not pid:
            continue
        permit = db.get_permit(pid)
        if not permit:
            continue
        if permit["status"] not in ("Sent", "Drip Sent", "Engaged"):
            continue

        scan_count = (permit["scan_count"] or 0) + 1
        extra = {
            "qr_scanned":    1,
            "scan_count":    scan_count,
        }
        if not permit["first_scan_date"]:
            extra["first_scan_date"] = scan.get("timestamp", db.now_iso())
        db.set_permit_status(pid, "Engaged", extra)
        engaged += 1
        log.info("Marked permit %s as Engaged (scan #%d)", pid, scan_count)

    log.info("Processed %d scan events → %d permits marked Engaged", len(scans), engaged)


# ── Exclusion processing (from WordPress) ─────────────────────────────────────

def process_exclusions():
    """Fetch exclusions from WordPress and mark those permits as Excluded in DB."""
    exclusions = _fetch_wp_json(EXCLUSIONS_URL)
    if not exclusions:
        return

    for excl in exclusions:
        pid = excl.get("pid")
        reason = excl.get("reason", "")
        if not pid:
            continue
        permit = db.get_permit(pid)
        if not permit:
            continue
        if permit["status"] == "Excluded":
            continue
        db.set_permit_status(pid, "Excluded", {
            "exclude_reason": reason,
            "excluded_by":    "email_link",
            "excluded_at":    excl.get("timestamp", db.now_iso()),
        })
        # Learn: create address exclusion rule
        db.upsert_exclusion_rule(CUSTOMER_ID, "Address", permit["property_address"], "Contains")
        log.info("Excluded permit %s (reason: %s)", pid, reason)


# ── Registry builder ───────────────────────────────────────────────────────────

def build_and_write_registry():
    """
    Write permit_registry.json: {pid: {owner_name, phone, address, permit_type}}
    Includes all Sent + Engaged permits. WordPress reads this for scan alert emails.
    """
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, owner_name, owner_phone, property_address, "
            "       property_city, property_zip, permit_type, is_new_construction "
            "FROM permits WHERE customer_id=? AND status IN ('Sent','Drip Sent','Engaged')",
            (CUSTOMER_ID,),
        ).fetchall()

    registry = {}
    for r in rows:
        registry[r["id"]] = {
            "owner_name":        r["owner_name"] or "",
            "phone":             r["owner_phone"] or "",
            "address":           f"{r['property_address'] or ''}, {r['property_city'] or ''} {r['property_zip'] or ''}".strip(", "),
            "permit_type":       r["permit_type"] or "",
            "is_new_construction": bool(r["is_new_construction"]),
        }

    db.write_registry(registry)
    log.info("Registry written with %d permits.", len(registry))
    return registry


# ── PURL URL builder ───────────────────────────────────────────────────────────

def _sign_pid(permit_id: str) -> str:
    """Generate HMAC-SHA256 signature for a permit ID."""
    import hmac, hashlib
    return hmac.new(
        config.PERMIT_MINER_HMAC_SECRET.encode(),
        permit_id.encode(),
        hashlib.sha256,
    ).hexdigest()


def build_purl_url(permit_id: str, is_drip: bool = False) -> str:
    campaign = "luxury_permits_drip" if is_drip else "luxury_permits"
    sig = _sign_pid(permit_id)
    return (
        f"{config.PURL_BASE_URL}"
        f"?pid={permit_id}"
        f"&sig={sig}"
        f"&utm_source=permit_miner"
        f"&utm_medium=direct_mail"
        f"&utm_campaign={campaign}"
        f"&utm_content={permit_id}"
    )


# ── Drip check ────────────────────────────────────────────────────────────────

def run_drip_check():
    """Queue second-touch drip records for permits sent >21 days ago with no scan."""
    cutoff = (date.today() - timedelta(days=config.DRIP_DELAY_DAYS)).isoformat()
    with db.get_conn() as conn:
        candidates = conn.execute(
            "SELECT * FROM permits WHERE customer_id=? AND status='Sent' "
            "AND touch_number=1 AND qr_scanned=0 AND postcard_sent_date <= ?",
            (CUSTOMER_ID, cutoff),
        ).fetchall()

    drip_count = 0
    for p in candidates:
        with db.get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM permits WHERE parent_permit_id=? AND touch_number=2",
                (p["id"],),
            ).fetchone()
        if existing:
            continue

        drip_id = db.new_id()
        purl_url = build_purl_url(drip_id, is_drip=True)
        ts = db.now_iso()
        with db.get_conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO permits
                   (id, customer_id, source, property_address, property_city,
                    property_state, property_zip, assessed_value_cents,
                    permit_type, permit_tags, is_new_construction,
                    owner_name, owner_type, contractor_name,
                    owner_phone, owner_email,
                    status, purl_url, touch_number, parent_permit_id,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (drip_id, CUSTOMER_ID, p["source"],
                 p["property_address"] + "__drip2",
                 p["property_city"], p["property_state"], p["property_zip"],
                 p["assessed_value_cents"],
                 p["permit_type"], p["permit_tags"], p["is_new_construction"],
                 p["owner_name"], p["owner_type"], p["contractor_name"],
                 p["owner_phone"], p["owner_email"],
                 "Drip Queued", purl_url, 2, p["id"], ts, ts),
            )
        drip_count += 1

    if drip_count:
        log.info("Drip check: queued %d second-touch records.", drip_count)


# ── Preview email ──────────────────────────────────────────────────────────────

def dollars(val: int) -> str:
    if not val:
        return "N/A"
    return f"${int(val):,.0f}"


def build_preview_email(new_permits: list[dict]) -> str:
    rows = ""
    for p in new_permits:
        pid = p["id"]
        # One-click exclude links — signed, reason in the URL, no form needed
        sig = _sign_pid(pid)
        ex_base = f"{config.WP_BASE_URL}/permit-exclude?pid={pid}&sig={sig}"
        exclude_links = (
            f'<a href="{ex_base}&reason=existing_customer" '
            f'style="background:#c0392b;color:#fff;padding:4px 9px;border-radius:3px;'
            f'text-decoration:none;font-size:10px;margin:1px;display:inline-block;">Existing customer</a>'
            f'<a href="{ex_base}&reason=not_homeowner" '
            f'style="background:#555;color:#fff;padding:4px 9px;border-radius:3px;'
            f'text-decoration:none;font-size:10px;margin:1px;display:inline-block;">Not homeowner</a>'
            f'<a href="{ex_base}&reason=wrong_project" '
            f'style="background:#555;color:#fff;padding:4px 9px;border-radius:3px;'
            f'text-decoration:none;font-size:10px;margin:1px;display:inline-block;">Wrong project</a>'
            f'<a href="{ex_base}&reason=already_contacted" '
            f'style="background:#555;color:#fff;padding:4px 9px;border-radius:3px;'
            f'text-decoration:none;font-size:10px;margin:1px;display:inline-block;">Already contacted</a>'
        )
        nc_badge = (
            " <span style='background:#e8943a;color:#fff;padding:2px 6px;"
            "border-radius:3px;font-size:10px;font-weight:bold;'>NEW BUILD</span>"
        ) if p.get("is_new_construction") else ""
        assessed_str = dollars(p.get("assessed_value_dollars") or (p.get("assessed_value_cents") or 0) // 100)
        rows += f"""
        <tr style="border-bottom:1px solid #eee;">
          <td style="padding:10px 8px;">
            <strong>{p.get('owner_name') or 'Unknown Owner'}</strong>{nc_badge}<br>
            <span style="font-size:12px;color:#555;">{p.get('property_address','')} {p.get('property_city','')} {p.get('property_zip','')}</span>
          </td>
          <td style="padding:10px 8px;font-size:12px;color:#555;white-space:nowrap;">
            {p.get('permit_type') or 'N/A'}
          </td>
          <td style="padding:10px 8px;font-size:12px;color:#555;white-space:nowrap;">
            {assessed_str}
          </td>
          <td style="padding:10px 8px;font-size:12px;color:#555;">
            {p.get('contractor_name') or 'N/A'}
          </td>
          <td style="padding:10px 8px;font-size:11px;">
            {exclude_links}
          </td>
        </tr>"""

    count = len(new_permits)
    today = str(date.today())
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#333;max-width:800px;margin:0 auto;">

<div style="background:#1a2744;padding:24px;color:#fff;">
  <span style="color:#e8943a;font-size:20px;font-weight:bold;">PERMIT MINER</span>
  <span style="float:right;font-size:13px;color:#aaa;">Week of {today}</span><br>
  <span style="font-size:15px;">Monday Preview — {count} permit{'s' if count != 1 else ''} queued for Tuesday send</span>
</div>

<div style="padding:12px 24px;font-size:13px;color:#666;background:#f9f9f9;border-bottom:1px solid #ddd;">
  Postcards send <strong>tomorrow (Tuesday) at 8AM</strong> unless excluded.
  Click a button to block a record before it mails — one click, no form.
</div>

<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
  <thead>
    <tr style="background:#f5f5f5;font-size:11px;color:#999;text-transform:uppercase;">
      <th style="padding:8px;text-align:left;">Owner / Address</th>
      <th style="padding:8px;text-align:left;">Permit Type</th>
      <th style="padding:8px;text-align:left;">Assessed Value</th>
      <th style="padding:8px;text-align:left;">Contractor</th>
      <th style="padding:8px;text-align:left;">Exclude</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>

{'<p style="padding:24px;color:#999;font-size:13px;text-align:center;">No new permits found this week.</p>' if count == 0 else ''}

<div style="padding:16px 24px;font-size:11px;color:#999;border-top:1px solid #eee;margin-top:24px;">
  Permit Miner | Livewire &nbsp;·&nbsp; {count} permit{'s' if count != 1 else ''} queued &nbsp;·&nbsp;
  Source: County permit portals + Virginia statewide data
</div>
</body></html>"""


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    log.info("=== Monday Pull started ===")
    db.init_db()

    # ── Step 1: Process scans from WordPress ──────────────────────────────────
    log.info("Step 1: Processing scans from WordPress...")
    process_scans()

    # ── Step 2: Process exclusions from WordPress ─────────────────────────────
    log.info("Step 2: Processing exclusions from WordPress...")
    process_exclusions()

    # ── Step 3: Determine lookback window ─────────────────────────────────────
    MIN_LOOKBACK = 7   # Always pull at least 7 days (covers weekly cadence + buffer)
    MAX_LOOKBACK = 30  # Cap at 30 days to avoid huge scrapes
    app_cfg = db.get_app_config(CUSTOMER_ID)
    if app_cfg and app_cfg["last_monday_run"]:
        since_days = (date.today() - date.fromisoformat(app_cfg["last_monday_run"])).days + 1
    else:
        since_days = 14  # First run: pull 2 weeks back
    since_days = max(MIN_LOOKBACK, min(since_days, MAX_LOOKBACK))
    log.info("Step 3: Pulling permits from last %d days", since_days)

    # ── Step 4: Collect permits from all sources ──────────────────────────────
    log.info("Step 4: Fetching from all scrapers...")
    all_raw: list[dict] = []

    # Virginia statewide CSV — primary source for most ZIPs
    try:
        va_permits = virginia_state.fetch_permits(since_days=since_days)
        all_raw.extend(va_permits)
        log.info("Virginia state CSV: %d permits", len(va_permits))
    except Exception as e:
        log.error("Virginia state CSV failed: %s", e)

    # Chesterfield — Accela portal (may have better data than state CSV)
    try:
        cf_permits = chesterfield.fetch_permits(since_days=since_days)
        all_raw.extend(cf_permits)
        log.info("Chesterfield: %d permits", len(cf_permits))
    except Exception as e:
        log.error("Chesterfield scraper failed: %s", e)

    # Goochland — EnerGov portal
    try:
        gl_permits = goochland.fetch_permits(since_days=since_days)
        all_raw.extend(gl_permits)
        log.info("Goochland: %d permits", len(gl_permits))
    except Exception as e:
        log.error("Goochland scraper failed: %s", e)

    # Powhatan — monthly PDF permit logs
    try:
        pw_permits = powhatan.fetch_permits(since_days=since_days)
        all_raw.extend(pw_permits)
        log.info("Powhatan: %d permits", len(pw_permits))
    except Exception as e:
        log.error("Powhatan scraper failed: %s", e)

    # Hanover — monthly PDF recap
    try:
        hv_permits = hanover.fetch_permits(since_days=since_days)
        all_raw.extend(hv_permits)
        log.info("Hanover: %d permits", len(hv_permits))
    except Exception as e:
        log.error("Hanover scraper failed: %s", e)

    log.info("Total raw permits collected: %d", len(all_raw))

    # ── Step 5: Filter + enrich + insert ──────────────────────────────────────
    log.info("Step 5: Filtering and inserting...")
    total_filtered = total_inserted = 0
    new_permits: list[dict] = []

    # Track addresses seen this run to dedup across scrapers
    seen_addresses: set[str] = set()

    for p in all_raw:
        owner = (p.get("owner_name") or "").strip()
        address = (p.get("property_address") or "").strip()
        zip_code = (p.get("property_zip") or "")[:5]

        if not address:
            total_filtered += 1
            continue

        # Powhatan PDFs don't include ZIP — assign based on county
        if not zip_code and p.get("source") == "Powhatan":
            zip_code = "23139"  # Default Powhatan ZIP (largest area)
            p["property_zip"] = zip_code
        elif not zip_code:
            total_filtered += 1
            continue

        # Dedup across scrapers (same address from VA CSV + county portal)
        addr_key = address.lower().strip()
        if addr_key in seen_addresses:
            total_filtered += 1
            continue
        seen_addresses.add(addr_key)

        # Skip companies / LLCs (but allow unknown/empty owners through —
        # county portals often don't include owner in search results;
        # owner will be enriched later via assessor lookup or Apollo)
        if owner and not owner_is_individual(owner):
            total_filtered += 1
            continue

        new_const = is_new_construction(p)

        # Tag / permit type filter
        if not new_const and not passes_tag_filter(p):
            total_filtered += 1
            continue

        # Value filter — try ArcGIS lookup if job_value is missing
        assessed = p.get("assessed_value_dollars") or 0
        if assessed == 0 and not new_const:
            assessed = get_assessed_value(address, zip_code)
            p["assessed_value_dollars"] = assessed

        if not passes_value_filter(p, new_const):
            total_filtered += 1
            continue

        # Exclusion rule check
        if db.is_excluded_by_rules({
            "contractor_name": p.get("contractor_name"),
            "permit_type": p.get("permit_type"),
            "permit_tags": p.get("description"),
            "property_address": address,
            "owner_name": owner,
        }, CUSTOMER_ID):
            total_filtered += 1
            continue

        # Apollo enrichment
        contact = enrich_via_apollo(owner, p.get("property_city", "Richmond"), "VA")

        permit_data = {
            "customer_id":           CUSTOMER_ID,
            "source":                p.get("source", "County Portal"),
            "property_address":      address,
            "property_city":         p.get("property_city", ""),
            "property_state":        p.get("property_state", "VA"),
            "property_zip":          zip_code,
            "assessed_value_cents":  int(assessed) * 100,
            "permit_type":           p.get("permit_type", ""),
            "permit_tags":           p.get("description", ""),
            "is_new_construction":   new_const,
            "file_date":             p.get("file_date", ""),
            "job_value_cents":       int(p.get("job_value_dollars") or 0) * 100,
            "owner_name":            owner,
            "owner_type":            "individual",
            "contractor_name":       p.get("contractor_name", ""),
            "owner_phone":           contact.get("owner_phone", ""),
            "owner_email":           contact.get("owner_email", ""),
            "owner_linkedin":        contact.get("owner_linkedin", ""),
            "status":                "Queued",
        }

        inserted, permit_id = db.upsert_permit(permit_data)
        if inserted:
            purl = build_purl_url(permit_id)
            db.set_permit_status(permit_id, "Queued", {"purl_url": purl})
            permit_data["id"] = permit_id
            permit_data["purl_url"] = purl
            permit_data["assessed_value_dollars"] = assessed
            new_permits.append(permit_data)
            total_inserted += 1
        else:
            log.debug("Dedup skip: %s", address)

    log.info(
        "Step 5 complete — raw: %d, filtered: %d, inserted: %d",
        len(all_raw), total_filtered, total_inserted,
    )

    # ── Step 6: Drip check ────────────────────────────────────────────────────
    log.info("Step 6: Running drip check...")
    run_drip_check()

    # ── Step 7: Write permit registry ─────────────────────────────────────────
    log.info("Step 7: Writing permit registry...")
    build_and_write_registry()

    # ── Step 8: Update last_monday_run ────────────────────────────────────────
    db.set_app_config_field("last_monday_run", str(date.today()))

    # ── Step 9: Send preview email ────────────────────────────────────────────
    log.info("Step 9: Sending preview email...")
    subject = f"Permit Miner Preview — {len(new_permits)} permit{'s' if len(new_permits) != 1 else ''} queued"
    html = build_preview_email(new_permits)
    send_email(config.PREVIEW_RECIPIENTS, subject, html)
    log.info("Preview email sent to %s", config.PREVIEW_RECIPIENTS)

    log.info("=== Monday Pull complete. %d new permits queued. ===", len(new_permits))


if __name__ == "__main__":
    run()
