"""
web/app.py — Permit Miner FastAPI web server.

Endpoints:
  GET  /exclude?pid={id}   — Renders exclude form with permit details
  POST /exclude            — Marks permit excluded, runs exclusion learning
  GET  /scan?pid={id}      — PURL QR scan tracker (called by purl_script.js)
  POST /booking            — Consultation booking webhook

Run locally:  uvicorn web.app:app --reload --port 8000
Production:   uvicorn web.app:app --host 0.0.0.0 --port 8000
"""
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

import config
import db
from pipeline.mailer import send_email

log = logging.getLogger(__name__)

app = FastAPI(title="Permit Miner", docs_url=None, redoc_url=None)

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

EXCLUDE_REASONS = [
    "Existing customer",
    "Not a homeowner (LLC / company)",
    "Outside target area",
    "Wrong contractor — not a target project",
    "Already have a relationship",
    "Low-value project",
    "Other",
]


# ── /exclude — GET ─────────────────────────────────────────────────────────────

@app.get("/exclude", response_class=HTMLResponse)
async def exclude_get(request: Request, pid: str = ""):
    permit = db.get_permit(pid) if pid else None
    if not permit:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;padding:40px;'>"
            "<h2>Permit not found.</h2>"
            "<p>This link may be invalid or the permit has already been excluded.</p>"
            "</body></html>",
            status_code=404,
        )
    return templates.TemplateResponse(
        "exclude_form.html",
        {
            "request": request,
            "permit": dict(permit),
            "reasons": EXCLUDE_REASONS,
            "already_excluded": permit["status"] == "Excluded",
        },
    )


# ── /exclude — POST ────────────────────────────────────────────────────────────

@app.post("/exclude", response_class=HTMLResponse)
async def exclude_post(
    pid: str = Form(...),
    reason: str = Form(...),
    custom_reason: str = Form(""),
):
    permit = db.get_permit(pid)
    if not permit:
        return HTMLResponse("<p>Permit not found.</p>", status_code=404)

    if permit["status"] == "Excluded":
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;padding:40px;'>"
            "<h2>Already excluded.</h2></body></html>"
        )

    final_reason = custom_reason.strip() if reason == "Other" and custom_reason.strip() else reason
    customer_id  = permit["customer_id"]

    # Update permit status
    db.set_permit_status(pid, "Excluded", {
        "exclude_reason": final_reason,
        "excluded_by":    "henry",
        "excluded_at":    db.now_iso(),
    })

    # ── Exclusion learning ────────────────────────────────────────────────────

    # 1. Address always blocklisted
    db.upsert_exclusion_rule(
        customer_id, "Address", (permit["property_address"] or "").lower(),
        match_type="Exact", auto_generated=False,
    )

    # 2. Owner Name blocklisted for "Existing customer"
    if reason == "Existing customer" and permit["owner_name"]:
        db.upsert_exclusion_rule(
            customer_id, "Owner_Name", permit["owner_name"].lower(),
            match_type="Exact", auto_generated=False,
        )

    # 3. Contractor: increment count, auto-blocklist at threshold
    if permit["contractor_name"]:
        db.upsert_exclusion_rule(
            customer_id, "Contractor", permit["contractor_name"].lower(),
            match_type="Contains", auto_generated=False,
        )
        count = db.get_contractor_exclusion_count(customer_id, permit["contractor_name"].lower())
        if count >= config.AUTO_BLOCK_THRESHOLD:
            # Ensure it's marked active (already done by upsert, but explicit)
            log.info("Auto-block threshold reached for contractor: %s (%d exclusions)",
                     permit["contractor_name"], count)

    log.info("Permit %s excluded — reason: %s", pid, final_reason)

    return HTMLResponse(
        "<html><head><meta charset='utf-8'></head>"
        "<body style='font-family:Arial,sans-serif;padding:40px;max-width:500px;margin:0 auto;'>"
        "<div style='background:#1a2744;padding:20px;color:#fff;border-radius:6px;'>"
        "<span style='color:#e8943a;font-weight:bold;font-size:18px;'>PERMIT MINER</span></div>"
        f"<h2 style='color:#1a2744;margin-top:24px;'>Excluded</h2>"
        f"<p style='color:#555;'><strong>{permit['property_address']}</strong> has been excluded.</p>"
        f"<p style='color:#888;font-size:13px;'>Reason: {final_reason}</p>"
        "<p style='color:#888;font-size:13px;'>You can close this tab.</p>"
        "</body></html>"
    )


# ── /scan — GET ────────────────────────────────────────────────────────────────

@app.get("/scan")
async def scan(pid: str = ""):
    """
    Called by purl_script.js on page load when a QR code is scanned.
    Returns JSON with permit_type so the PURL page can swap content.
    """
    if not pid:
        return JSONResponse({"status": "error", "message": "Missing pid"}, status_code=400)

    permit = db.get_permit(pid)
    if not permit:
        return JSONResponse({"status": "error", "message": "Permit not found"}, status_code=404)

    now = db.now_iso()
    updates: dict = {"scan_count": (permit["scan_count"] or 0) + 1}

    if not permit["qr_scanned"]:
        updates["qr_scanned"]       = 1
        updates["first_scan_date"]  = now
        if permit["status"] == "Sent":
            updates["status"] = "Engaged"

        # Send scan alert email
        _send_scan_alert(dict(permit))
        log.info("PURL scan recorded for permit %s — first scan", pid)
    else:
        log.info("PURL scan recorded for permit %s — repeat scan #%d", pid, updates["scan_count"])

    db.set_permit_status(pid, updates.get("status", permit["status"]), updates)

    return JSONResponse({
        "status":      "ok",
        "permit_type": permit["permit_type"] or "",
        "is_new_construction": bool(permit["is_new_construction"]),
        "tags":        permit["permit_tags"] or "[]",
    })


def _send_scan_alert(permit: dict):
    owner  = permit.get("owner_name") or "Unknown Owner"
    addr   = permit.get("property_address") or ""
    ptype  = permit.get("permit_type") or "N/A"
    value  = permit.get("assessed_value_cents")
    phone  = permit.get("owner_phone") or ""
    email  = permit.get("owner_email") or ""

    def dollars(cents) -> str:
        return f"${int(cents)/100:,.0f}" if cents else "N/A"

    phone_html = (
        f'<a href="tel:{phone}" style="font-size:28px;font-weight:bold;color:#fff;text-decoration:none;">{phone}</a>'
        if phone else '<span style="font-size:18px;color:#aaa;">No phone on file</span>'
    )
    email_html = f'<a href="mailto:{email}" style="color:#e8943a;">{email}</a>' if email else "N/A"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#333;max-width:600px;margin:0 auto;">

<div style="background:#27ae60;padding:20px 24px;color:#fff;">
  <span style="font-size:11px;text-transform:uppercase;letter-spacing:1px;">QR Code Scanned</span><br>
  <span style="font-size:22px;font-weight:bold;">{owner}</span>
</div>

<div style="background:#1a2744;padding:24px;text-align:center;">
  {phone_html}
  <div style="font-size:11px;color:#aaa;margin-top:8px;">CALL NOW</div>
</div>

<div style="padding:20px 24px;">
  <table width="100%" style="font-size:13px;border-collapse:collapse;">
    <tr><td style="padding:6px 0;color:#888;width:140px;">Address</td>
        <td style="padding:6px 0;font-weight:bold;">{addr}</td></tr>
    <tr><td style="padding:6px 0;color:#888;">Permit Type</td>
        <td style="padding:6px 0;">{ptype}</td></tr>
    <tr><td style="padding:6px 0;color:#888;">Assessed Value</td>
        <td style="padding:6px 0;">{dollars(value)}</td></tr>
    <tr><td style="padding:6px 0;color:#888;">Email</td>
        <td style="padding:6px 0;">{email_html}</td></tr>
  </table>
</div>

<div style="padding:0 24px 24px;">
  <a href="{config.BASE_URL}/exclude?pid={permit['id']}"
     style="background:#c0392b;color:#fff;padding:10px 20px;border-radius:4px;text-decoration:none;font-size:13px;">
    Exclude This Record
  </a>
</div>

<div style="padding:16px 24px;font-size:11px;color:#999;border-top:1px solid #eee;">
  Permit Miner | Livewire
</div>
</body></html>"""

    send_email(
        config.ALERT_RECIPIENTS,
        f"🔔 QR Scan — {owner} ({addr})",
        html,
    )


# ── /booking — POST ────────────────────────────────────────────────────────────

@app.post("/booking")
async def booking(request: Request):
    """
    Webhook for consultation bookings (Zoho Bookings, Calendly, etc.).
    Matches permit by pid, email, or phone. Updates to Consultation Scheduled.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)

    pid   = body.get("pid") or body.get("permit_id")
    email = (body.get("email") or body.get("customer_email") or "").lower()
    phone = body.get("phone") or body.get("customer_phone") or ""

    permit = None

    if pid:
        permit = db.get_permit(pid)

    if not permit and email:
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM permits WHERE customer_id=? AND LOWER(owner_email)=? LIMIT 1",
                ("livewire", email),
            ).fetchone()
            if row:
                permit = row

    if not permit and phone:
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM permits WHERE customer_id=? AND owner_phone=? LIMIT 1",
                ("livewire", phone),
            ).fetchone()
            if row:
                permit = row

    if not permit:
        log.warning("Booking webhook: no permit matched — pid=%s email=%s phone=%s", pid, email, phone)
        return JSONResponse({"status": "no_match"}, status_code=200)

    db.set_permit_status(permit["id"], "Consultation Scheduled", {
        "updated_at": db.now_iso(),
    })
    log.info("Consultation scheduled for permit %s (%s)", permit["id"], permit["property_address"])

    return JSONResponse({"status": "ok", "permit_id": permit["id"]})


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "mode": config.MODE}
