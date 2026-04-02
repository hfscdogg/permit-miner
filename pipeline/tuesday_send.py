"""
tuesday_send.py — Permit Miner Tuesday 8AM pipeline.

1. Fetch exclusions from Zoho → mark excluded permits in DB
2. Send Lob postcards for Queued + Drip Queued permits
3. Push updated permit registry to Zoho (for stateless scan lookups)
4. Email Henry and sales team a digest

Run:  python -m pipeline.tuesday_send
Cron: 0 13 * * 2  (8AM ET = 13:00 UTC, Tuesday)
"""
import base64
import json
import logging
from datetime import date

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


# ── Lob API ────────────────────────────────────────────────────────────────────

def lob_auth_header() -> dict:
    """Lob uses HTTP Basic Auth: API key as username, empty password."""
    token = base64.b64encode(f"{config.LOB_API_KEY}:".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def send_lob_postcard(permit: dict, is_drip: bool = False) -> tuple[bool, str, str]:
    """
    POST a postcard to Lob. Returns (success, postcard_id, tracking_url).
    In test mode uses test API key (Lob won't actually print).
    """
    owner_name = permit["owner_name"] or "Homeowner"
    # Split into first name for greeting
    first_name = owner_name.split()[0].title() if owner_name else "Homeowner"

    front_template = config.LOB_DRIP_TEMPLATE_FRONT_ID if is_drip else config.LOB_TEMPLATE_FRONT_ID
    back_template  = config.LOB_DRIP_TEMPLATE_BACK_ID  if is_drip else config.LOB_TEMPLATE_BACK_ID

    payload = {
        "description": f"Permit Miner — {permit['id']}",
        "size": config.POSTCARD_SIZE,
        "front": front_template,
        "back":  back_template,
        "to": {
            "name":          owner_name,
            "address_line1": permit.get("property_address", "").split(",")[0].strip(),
            "address_city":  permit.get("property_city", ""),
            "address_state": permit.get("property_state", "VA"),
            "address_zip":   permit.get("property_zip", ""),
            "address_country": "US",
        },
        "from": {
            "name":          config.RETURN_NAME,
            "address_line1": config.RETURN_ADDRESS,
            "address_city":  config.RETURN_CITY,
            "address_state": config.RETURN_STATE,
            "address_zip":   config.RETURN_ZIP,
            "address_country": "US",
        },
        "merge_variables": {
            "name":           first_name,
            "address_line1":  permit.get("property_address", "").split(",")[0].strip(),
            "address_city":   permit.get("property_city", ""),
            "address_state":  permit.get("property_state", "VA"),
            "address_zip":    permit.get("property_zip", ""),
            "qr_url":         permit.get("purl_url", ""),
        },
    }

    if config.MODE == "test":
        log.info("[TEST] Would send Lob postcard to %s at %s (pid=%s)",
                 owner_name, permit.get("property_address"), permit["id"])
        return True, f"psc_test_{permit['id']}", ""

    try:
        r = httpx.post(
            f"{config.LOB_BASE_URL}/postcards",
            headers=lob_auth_header(),
            content=json.dumps(payload),
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        postcard_id   = data.get("id", "")
        tracking_url  = data.get("url", "")
        log.info("Lob postcard sent: %s → %s", permit["id"], postcard_id)
        return True, postcard_id, tracking_url
    except httpx.HTTPStatusError as e:
        log.error("Lob API error for permit %s: %s — %s", permit["id"], e, e.response.text)
        return False, "", str(e)
    except Exception as e:
        log.error("Lob send failed for permit %s: %s", permit["id"], e)
        return False, "", str(e)


# ── Sales digest email ──────────────────────────────────────────────────────────

def dollars(cents) -> str:
    if not cents:
        return "N/A"
    return f"${int(cents) / 100:,.0f}"


def build_digest_email(sent_permits: list[dict], error_count: int) -> str:
    rows = ""
    for p in sent_permits:
        phone_html = f'<a href="tel:{p["owner_phone"]}" style="color:#1a2744;">{p["owner_phone"]}</a>' if p.get("owner_phone") else "N/A"
        email_html = f'<a href="mailto:{p["owner_email"]}" style="color:#1a2744;">{p["owner_email"]}</a>' if p.get("owner_email") else "N/A"
        exclude_url = f"{config.WP_BASE_URL}/permit-exclude?pid={p['id']}"
        nc_badge = " <span style='background:#e8943a;color:#fff;padding:2px 5px;border-radius:3px;font-size:10px;'>NEW BUILD</span>" if p.get("is_new_construction") else ""
        touch_badge = f" <span style='background:#6c757d;color:#fff;padding:2px 5px;border-radius:3px;font-size:10px;'>DRIP #{p.get('touch_number',1)}</span>" if p.get("touch_number", 1) > 1 else ""

        rows += f"""
        <tr style="border-bottom:1px solid #f0f0f0;">
          <td style="padding:10px 8px;">
            <strong>{p.get('owner_name') or 'Unknown'}</strong>{nc_badge}{touch_badge}<br>
            <span style="font-size:11px;color:#666;">{p.get('property_address','')} · {p.get('property_zip','')}</span>
          </td>
          <td style="padding:10px 8px;font-size:12px;">{p.get('permit_type') or 'N/A'}</td>
          <td style="padding:10px 8px;font-size:12px;">{dollars(p.get('assessed_value_cents'))}</td>
          <td style="padding:10px 8px;font-size:12px;">{p.get('contractor_name') or 'N/A'}</td>
          <td style="padding:10px 8px;font-size:12px;">{phone_html}<br>{email_html}</td>
          <td style="padding:10px 8px;">
            <a href="{exclude_url}" style="background:#c0392b;color:#fff;padding:4px 10px;border-radius:3px;text-decoration:none;font-size:11px;">Exclude</a>
          </td>
        </tr>"""

    count = len(sent_permits)
    today = str(date.today())
    error_note = f'<p style="color:#c0392b;padding:0 24px;font-size:12px;">⚠ {error_count} postcard(s) failed to send — check logs.</p>' if error_count else ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#333;max-width:750px;margin:0 auto;">

<div style="background:#1a2744;padding:24px;color:#fff;">
  <span style="color:#e8943a;font-size:20px;font-weight:bold;">PERMIT MINER</span>
  <span style="float:right;font-size:13px;color:#aaa;">{today}</span><br>
  <span style="font-size:15px;">Tuesday Digest — {count} postcard{'s' if count != 1 else ''} sent</span>
</div>

{error_note}

<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
  <thead>
    <tr style="background:#f5f5f5;font-size:10px;color:#999;text-transform:uppercase;">
      <th style="padding:8px;text-align:left;">Owner / Address</th>
      <th style="padding:8px;text-align:left;">Permit</th>
      <th style="padding:8px;text-align:left;">Value</th>
      <th style="padding:8px;text-align:left;">Contractor</th>
      <th style="padding:8px;text-align:left;">Contact</th>
      <th style="padding:8px;"></th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>

{'<p style="padding:24px;color:#999;font-size:13px;text-align:center;">No postcards sent this week.</p>' if count == 0 else ''}

<div style="padding:16px 24px;font-size:11px;color:#999;border-top:1px solid #eee;margin-top:24px;">
  Permit Miner | Livewire &nbsp;·&nbsp; Postcards typically arrive 3–5 business days after send date.
</div>
</body></html>"""


# ── Zoho exclusions sync ──────────────────────────────────────────────────────

def fetch_and_apply_exclusions():
    """
    Fetch pending exclusions from Zoho API and mark permits Excluded in DB.
    Exclusion events are relayed to Zoho by the WordPress plugin on each
    /permit-exclude request.
    """
    if not config.ZOHO_WEBHOOK_URL or not config.ZOHO_API_TOKEN:
        log.info("Zoho API not configured -- skipping exclusion sync.")
        return

    try:
        r = httpx.get(
            config.ZOHO_WEBHOOK_URL,
            params={"event": "exclusions"},
            headers={"Authorization": f"Zoho-oauthtoken {config.ZOHO_API_TOKEN}"},
            timeout=15,
        )
        if r.status_code != 200:
            log.info("Zoho exclusions fetch: %d -- skipping", r.status_code)
            return
        exclusions = r.json()
        if not isinstance(exclusions, list) or not exclusions:
            log.info("No Zoho exclusions to process.")
            return
    except Exception as e:
        log.warning("Could not fetch Zoho exclusions: %s", e)
        return

    applied = 0
    for excl in exclusions:
        pid = excl.get("pid")
        reason = excl.get("reason", "")
        if not pid:
            continue
        permit = db.get_permit(pid)
        if not permit or permit["status"] == "Excluded":
            continue
        db.set_permit_status(pid, "Excluded", {
            "exclude_reason": reason,
            "excluded_by":    "email_link",
            "excluded_at":    excl.get("timestamp", db.now_iso()),
        })
        db.upsert_exclusion_rule(CUSTOMER_ID, "Address", permit["property_address"], "Contains")
        applied += 1
        log.info("Excluded permit %s via Zoho (reason: %s)", pid, reason)

    log.info("Applied %d exclusions from Zoho.", applied)


# ── Zoho registry push ─────────────────────────────────────────────────────────

def push_registry_to_zoho(registry: dict):
    """
    POST permit registry to Zoho so the WordPress scan endpoint can look up
    permits via server-to-server Zoho API call.
    """
    if not config.ZOHO_WEBHOOK_URL or not config.ZOHO_API_TOKEN:
        log.warning("Zoho API not configured -- skipping registry push.")
        return
    if not registry:
        return

    try:
        r = httpx.post(
            config.ZOHO_WEBHOOK_URL,
            json={"event": "registry_update", "registry": registry},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Zoho-oauthtoken {config.ZOHO_API_TOKEN}",
            },
            timeout=30,
        )
        if r.status_code in (200, 201):
            log.info("Registry pushed to Zoho (%d permits).", len(registry))
        else:
            log.warning("Zoho registry push returned %d: %s", r.status_code, r.text[:200])
    except Exception as e:
        log.warning("Zoho registry push failed: %s", e)


def build_registry_from_sent(sent_permits: list[dict]) -> dict:
    """Build registry dict from newly sent permits + existing DB registry."""
    # Start with current registry from DB
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
    return registry


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    log.info("=== Tuesday Send started ===")
    db.init_db()

    # ── Step 1: Apply exclusions from Zoho ──────────────────────────────────
    log.info("Step 1: Fetching exclusions from Zoho...")
    fetch_and_apply_exclusions()

    queued = db.get_queued_permits(CUSTOMER_ID)
    log.info("%d permit(s) queued for send.", len(queued))

    sent_permits = []
    error_count  = 0
    today_str    = str(date.today())

    for p in queued:
        permit = dict(p)
        is_drip = permit.get("touch_number", 1) > 1

        ok, postcard_id, tracking_url = send_lob_postcard(permit, is_drip=is_drip)

        if ok:
            new_status = "Drip Sent" if is_drip else "Sent"
            db.set_permit_status(permit["id"], new_status, {
                "lob_postcard_id":    postcard_id,
                "lob_tracking_url":   tracking_url,
                "postcard_sent_date": today_str,
            })
            permit["lob_postcard_id"] = postcard_id
            sent_permits.append(permit)
        else:
            db.set_permit_status(permit["id"], "Lob Error", {
                "lob_error": tracking_url,  # reused field carries error message
            })
            error_count += 1

    log.info("Send complete — sent: %d, errors: %d", len(sent_permits), error_count)

    # ── Update last_tuesday_run ─────────────────────────────────────────────────
    db.set_app_config_field("last_tuesday_run", today_str)

    # ── Push registry to Zoho ─────────────────────────────────────────────────
    log.info("Pushing registry to Zoho...")
    registry = build_registry_from_sent(sent_permits)
    db.write_registry(registry)
    push_registry_to_zoho(registry)

    # ── Sales digest email ──────────────────────────────────────────────────────
    subject = f"Permit Miner — {len(sent_permits)} postcard{'s' if len(sent_permits) != 1 else ''} sent today"
    html = build_digest_email(sent_permits, error_count)
    send_email(config.DIGEST_RECIPIENTS, subject, html)
    log.info("Digest email sent to %s", config.DIGEST_RECIPIENTS)

    log.info("=== Tuesday Send complete ===")


if __name__ == "__main__":
    run()
