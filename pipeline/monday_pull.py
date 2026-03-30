"""
monday_pull.py — Permit Miner Monday 8AM pipeline.

Pulls permits from Shovels API for all configured ZIP codes,
filters by value + owner type + tags + exclusion rules,
enriches with contact data, stores as Queued in SQLite,
then sends the Monday preview email to Henry with Exclude buttons.

Run:  python -m pipeline.monday_pull
Cron: 0 8 * * 1  (Monday 8:00 AM ET — set TZ=America/New_York in cron env)
"""
import json
import logging
import sys
from datetime import date, timedelta

import httpx

import config
import db
from pipeline.mailer import send_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

CUSTOMER_ID = "livewire"


# ── Shovels API helpers ────────────────────────────────────────────────────────

def shovels_headers() -> dict:
    return {"X-API-Key": config.SHOVELS_API_KEY, "Accept": "application/json"}


def fetch_permits_for_zip(zip_code: str, since_date: str) -> list[dict]:
    """
    Cursor-paginate through /v2/permits/search for one ZIP.
    Returns a flat list of raw permit dicts.
    """
    url = f"{config.SHOVELS_BASE_URL}/permits/search"
    permits = []
    cursor = None

    while True:
        params = {
            "zip_code": zip_code,
            "file_date_after": since_date,
            "size": config.SHOVELS_PAGE_SIZE,
        }
        if cursor:
            params["cursor"] = cursor

        try:
            r = httpx.get(url, headers=shovels_headers(), params=params, timeout=30)
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.error("Shovels API error for ZIP %s: %s", zip_code, e)
            # Retry once
            try:
                r = httpx.get(url, headers=shovels_headers(), params=params, timeout=30)
                r.raise_for_status()
            except httpx.HTTPError as e2:
                log.error("Shovels retry failed for ZIP %s: %s", zip_code, e2)
                break

        payload = r.json()
        page_permits = payload.get("permits") or payload.get("results") or []
        permits.extend(page_permits)
        log.debug("ZIP %s — fetched %d permits (page total: %d)", zip_code, len(page_permits), len(permits))

        cursor = payload.get("next_cursor") or payload.get("cursor")
        if not cursor or not page_permits:
            break

    return permits


def fetch_residents(address_id: str) -> dict:
    """Fetch contact enrichment from /addresses/{address_id}/residents."""
    if not address_id:
        return {}
    url = f"{config.SHOVELS_BASE_URL}/addresses/{address_id}/residents"
    try:
        r = httpx.get(url, headers=shovels_headers(), timeout=20)
        if r.status_code == 200:
            data = r.json()
            residents = data.get("residents") or []
            if residents:
                # Take the first individual resident
                res = residents[0]
                return {
                    "owner_phone":        res.get("phone"),
                    "owner_email":        res.get("email"),
                    "owner_linkedin":     res.get("linkedin_url"),
                    "owner_income_range": res.get("income_range"),
                    "owner_net_worth":    res.get("net_worth"),
                }
    except Exception as e:
        log.debug("Residents lookup failed for address %s: %s", address_id, e)
    return {}


def fetch_contractor_name(contractor_id: str) -> tuple[str, str, str]:
    """Returns (name, phone, email) for a contractor ID."""
    if not contractor_id:
        return "", "", ""
    url = f"{config.SHOVELS_BASE_URL}/contractors"
    try:
        r = httpx.get(url, headers=shovels_headers(), params={"id": contractor_id}, timeout=20)
        if r.status_code == 200:
            data = r.json()
            contractors = data.get("contractors") or data.get("results") or []
            if contractors:
                c = contractors[0]
                return (
                    c.get("name") or c.get("company_name") or "",
                    c.get("phone") or "",
                    c.get("email") or "",
                )
    except Exception as e:
        log.debug("Contractor lookup failed for %s: %s", contractor_id, e)
    return "", "", ""


# ── Filtering logic ────────────────────────────────────────────────────────────

def is_new_construction(permit: dict) -> bool:
    tags = permit.get("tags") or []
    if isinstance(tags, str):
        tags = json.loads(tags)
    tag_set = {t.lower() for t in tags}
    if tag_set & config.NEW_CONSTRUCTION_TAGS:
        return True
    permit_type = (permit.get("type") or permit.get("permit_type") or "").lower()
    return any(kw in permit_type for kw in config.NEW_CONSTRUCTION_TYPE_KEYWORDS)


def passes_tag_filter(permit: dict) -> bool:
    tags = permit.get("tags") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = []
    tag_set = {t.lower() for t in tags}
    qualifying = {t.lower() for t in config.QUALIFYING_TAGS}
    return bool(tag_set & qualifying)


def passes_value_filter(permit: dict, new_construction: bool) -> bool:
    if new_construction:
        return True   # Always include — vacant land has $0 assessed value
    assessed = permit.get("property_assess_market_value") or 0
    return assessed >= config.MIN_ASSESSED_VALUE_CENTS


def owner_is_individual(permit: dict) -> bool:
    owner_type = (permit.get("property_owner_type") or "").lower()
    return owner_type == "individual"


# ── Address string normalization ───────────────────────────────────────────────

def build_address_string(permit: dict) -> str:
    parts = [
        permit.get("property_address") or permit.get("address") or "",
        permit.get("property_city") or permit.get("city") or "",
        permit.get("property_state") or permit.get("state") or "",
        permit.get("property_zip") or permit.get("zip_code") or "",
    ]
    return ", ".join(p for p in parts if p).strip()


# ── PURL URL builder ───────────────────────────────────────────────────────────

def build_purl_url(permit_id: str, is_drip: bool = False) -> str:
    campaign = "luxury_permits_drip" if is_drip else "luxury_permits"
    return (
        f"{config.PURL_BASE_URL}"
        f"?pid={permit_id}"
        f"&utm_source=permit_miner"
        f"&utm_medium=direct_mail"
        f"&utm_campaign={campaign}"
        f"&utm_content={permit_id}"
    )


# ── Drip check ────────────────────────────────────────────────────────────────

def run_drip_check():
    """
    Find Sent records older than DRIP_DELAY_DAYS with no scan (touch_number=1)
    and create Drip Queued records for second-touch send on Tuesday.
    """
    if not True:  # Drip disabled by default — guard with config flag if desired
        return
    cutoff = (date.today() - timedelta(days=config.DRIP_DELAY_DAYS)).isoformat()
    with db.get_conn() as conn:
        candidates = conn.execute(
            """SELECT * FROM permits
               WHERE customer_id=? AND status='Sent'
               AND touch_number=1 AND qr_scanned=0
               AND postcard_sent_date <= ?""",
            (CUSTOMER_ID, cutoff),
        ).fetchall()

    drip_count = 0
    for p in candidates:
        # Check max touches not exceeded
        with db.get_conn() as conn:
            existing_drip = conn.execute(
                "SELECT id FROM permits WHERE parent_permit_id=? AND touch_number=2",
                (p["id"],),
            ).fetchone()
        if existing_drip:
            continue

        drip_id = db.new_id()
        purl_url = build_purl_url(drip_id, is_drip=True)
        drip_data = {
            "id": drip_id,
            "customer_id": CUSTOMER_ID,
            "shovels_permit_id": p["shovels_permit_id"],
            "source": p["source"],
            "property_address": p["property_address"] + "__drip2",  # avoid UNIQUE collision
            "property_city": p["property_city"],
            "property_state": p["property_state"],
            "property_zip": p["property_zip"],
            "assessed_value_cents": p["assessed_value_cents"],
            "permit_type": p["permit_type"],
            "permit_tags": p["permit_tags"],
            "is_new_construction": p["is_new_construction"],
            "owner_name": p["owner_name"],
            "owner_type": p["owner_type"],
            "contractor_name": p["contractor_name"],
            "owner_phone": p["owner_phone"],
            "owner_email": p["owner_email"],
            "status": "Drip Queued",
            "purl_url": purl_url,
            "touch_number": 2,
            "parent_permit_id": p["id"],
        }
        ts = db.now_iso()
        with db.get_conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO permits
                   (id, customer_id, shovels_permit_id, source,
                    property_address, property_city, property_state, property_zip,
                    assessed_value_cents, permit_type, permit_tags, is_new_construction,
                    owner_name, owner_type, contractor_name,
                    owner_phone, owner_email,
                    status, purl_url, touch_number, parent_permit_id,
                    created_at, updated_at)
                   VALUES
                   (:id, :customer_id, :shovels_permit_id, :source,
                    :property_address, :property_city, :property_state, :property_zip,
                    :assessed_value_cents, :permit_type, :permit_tags, :is_new_construction,
                    :owner_name, :owner_type, :contractor_name,
                    :owner_phone, :owner_email,
                    :status, :purl_url, :touch_number, :parent_permit_id,
                    :created_at, :updated_at)""",
                {**drip_data, "created_at": ts, "updated_at": ts},
            )
        drip_count += 1
    if drip_count:
        log.info("Drip check: queued %d second-touch records.", drip_count)


# ── Preview email ──────────────────────────────────────────────────────────────

def dollars(cents: int) -> str:
    if not cents:
        return "N/A"
    return f"${cents / 100:,.0f}"


def build_preview_email(new_permits: list[dict]) -> str:
    rows = ""
    for p in new_permits:
        exclude_url = f"{config.BASE_URL}/exclude?pid={p['id']}"
        nc_badge = " <span style='background:#e8943a;color:#fff;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:bold;'>NEW BUILD</span>" if p.get("is_new_construction") else ""
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
            {dollars(p.get('assessed_value_cents'))}
          </td>
          <td style="padding:10px 8px;font-size:12px;color:#555;">
            {p.get('contractor_name') or 'N/A'}
          </td>
          <td style="padding:10px 8px;">
            <a href="{exclude_url}" style="background:#c0392b;color:#fff;padding:5px 12px;border-radius:4px;text-decoration:none;font-size:11px;font-weight:bold;">Exclude</a>
          </td>
        </tr>"""

    count = len(new_permits)
    today = str(date.today())
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#333;max-width:700px;margin:0 auto;">

<div style="background:#1a2744;padding:24px;color:#fff;">
  <span style="color:#e8943a;font-size:20px;font-weight:bold;">PERMIT MINER</span>
  <span style="float:right;font-size:13px;color:#aaa;">Week of {today}</span><br>
  <span style="font-size:15px;">Monday Preview — {count} permit{'s' if count != 1 else ''} queued for Tuesday send</span>
</div>

<div style="padding:16px 0;font-size:13px;color:#666;background:#f9f9f9;padding:12px 24px;border-bottom:1px solid #ddd;">
  Postcards send <strong>tomorrow (Tuesday) at 8AM</strong> unless excluded.
  Tap <strong>Exclude</strong> to block a record before it mails.
</div>

<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
  <thead>
    <tr style="background:#f5f5f5;font-size:11px;color:#999;text-transform:uppercase;">
      <th style="padding:8px;text-align:left;">Owner / Address</th>
      <th style="padding:8px;text-align:left;">Permit Type</th>
      <th style="padding:8px;text-align:left;">Assessed Value</th>
      <th style="padding:8px;text-align:left;">Contractor</th>
      <th style="padding:8px;"></th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>

{'<p style="padding:24px;color:#999;font-size:13px;text-align:center;">No new permits found this week.</p>' if count == 0 else ''}

<div style="padding:16px 24px;font-size:11px;color:#999;border-top:1px solid #eee;margin-top:24px;">
  Permit Miner | Livewire &nbsp;·&nbsp; {count} permit{'s' if count != 1 else ''} queued
</div>
</body></html>"""


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    log.info("=== Monday Pull started ===")
    db.init_db()

    # Determine since_date: last Monday run or 7 days ago
    app_cfg = db.get_app_config(CUSTOMER_ID)
    if app_cfg and app_cfg["last_monday_run"]:
        since_date = app_cfg["last_monday_run"]
    else:
        since_date = (date.today() - timedelta(days=7)).isoformat()
    log.info("Pulling permits filed since %s", since_date)

    total_found = total_inserted = total_filtered = 0
    new_permits = []

    for zip_code in config.ZIP_CODES:
        if zip_code in config.HENRICO_ZIPS:
            log.info("ZIP %s — skipping (Henrico Direct, handled by henrico_import)", zip_code)
            continue

        log.info("ZIP %s — fetching...", zip_code)
        raw_permits = fetch_permits_for_zip(zip_code, since_date)
        log.info("ZIP %s — %d raw permits returned", zip_code, len(raw_permits))
        total_found += len(raw_permits)

        for p in raw_permits:
            # ── Filters ──────────────────────────────────────────────────────
            if not owner_is_individual(p):
                total_filtered += 1
                continue

            new_const = is_new_construction(p)

            if not passes_value_filter(p, new_const):
                total_filtered += 1
                continue

            if not passes_tag_filter(p):
                total_filtered += 1
                continue

            # ── Build record dict ─────────────────────────────────────────
            address = build_address_string(p)
            if not address:
                total_filtered += 1
                continue

            tags = p.get("tags") or []
            if isinstance(tags, list):
                tags_str = json.dumps(tags)
            else:
                tags_str = str(tags)

            permit_data = {
                "customer_id":           CUSTOMER_ID,
                "shovels_permit_id":     p.get("id") or p.get("permit_id"),
                "source":                "Shovels",
                "property_address":      address,
                "property_city":         p.get("property_city") or p.get("city"),
                "property_state":        p.get("property_state") or p.get("state"),
                "property_zip":          p.get("property_zip") or p.get("zip_code") or zip_code,
                "assessed_value_cents":  p.get("property_assess_market_value") or 0,
                "shovels_address_id":    (p.get("geo_ids") or {}).get("address_id") or p.get("address_id"),
                "permit_type":           p.get("type") or p.get("permit_type"),
                "permit_tags":           tags_str,
                "is_new_construction":   new_const,
                "file_date":             p.get("file_date"),
                "job_value_cents":       p.get("job_value") or 0,
                "owner_name":            p.get("property_legal_owner") or p.get("owner_name"),
                "owner_type":            p.get("property_owner_type"),
                "contractor_id":         p.get("contractor_id"),
                "status":                "Queued",
            }

            # ── Exclusion rule check ──────────────────────────────────────
            if db.is_excluded_by_rules(permit_data, CUSTOMER_ID):
                log.debug("Permit at %s matched exclusion rule — skipping.", address)
                total_filtered += 1
                continue

            # ── Contact enrichment ────────────────────────────────────────
            address_id = permit_data.get("shovels_address_id")
            if address_id:
                contact = fetch_residents(address_id)
                permit_data.update(contact)

            # ── Contractor lookup ─────────────────────────────────────────
            if permit_data.get("contractor_id"):
                c_name, c_phone, c_email = fetch_contractor_name(permit_data["contractor_id"])
                permit_data["contractor_name"]  = c_name
                permit_data["contractor_phone"] = c_phone
                permit_data["contractor_email"] = c_email

            # ── Insert (dedup by property_address) ────────────────────────
            inserted, permit_id = db.upsert_permit(permit_data)
            if inserted:
                permit_data["id"] = permit_id
                purl = build_purl_url(permit_id)
                db.set_permit_status(permit_id, "Queued", {"purl_url": purl})
                permit_data["purl_url"] = purl
                new_permits.append(permit_data)
                total_inserted += 1
            else:
                log.debug("Dedup skip: %s", address)

    log.info("Pull complete — found: %d, filtered: %d, inserted: %d",
             total_found, total_filtered, total_inserted)

    # ── Drip check ─────────────────────────────────────────────────────────────
    run_drip_check()

    # ── Update last_monday_run ─────────────────────────────────────────────────
    db.set_app_config_field("last_monday_run", str(date.today()))

    # ── Send preview email ─────────────────────────────────────────────────────
    if new_permits or True:  # always send so Henry knows the job ran
        subject = f"Permit Miner Preview — {len(new_permits)} permit{'s' if len(new_permits) != 1 else ''} queued"
        html = build_preview_email(new_permits)
        send_email(config.PREVIEW_RECIPIENTS, subject, html)
        log.info("Preview email sent to %s", config.PREVIEW_RECIPIENTS)
    else:
        log.info("No new permits — preview email suppressed.")

    log.info("=== Monday Pull complete ===")


if __name__ == "__main__":
    run()
