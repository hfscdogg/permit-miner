"""
monthly_report.py — Permit Miner monthly learning report.

Runs on the 1st of each month. Aggregates funnel metrics from the
previous month, exclusion reasons, top excluded contractors, ZIP
performance, and cost estimates. Emails report to preview recipients.

Run:  python -m pipeline.monthly_report
Cron: 0 9 1 * *  (1st of month, 9:00 AM ET)
"""
import json
import logging
from datetime import date, timedelta
from calendar import monthrange

import config
import db
from pipeline.mailer import send_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

CUSTOMER_ID = "livewire"

# Approximate cost per postcard (Lob 6x11 + postage)
COST_PER_POSTCARD = 1.85


def prev_month_range() -> tuple[str, str]:
    """Return (first_day, last_day) ISO strings for the previous calendar month."""
    today = date.today()
    first_this = today.replace(day=1)
    last_prev  = first_this - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return str(first_prev), str(last_prev)


def run():
    log.info("=== Monthly Report started ===")
    db.init_db()

    start_date, end_date = prev_month_range()
    month_label = date.fromisoformat(start_date).strftime("%B %Y")
    log.info("Reporting on: %s (%s to %s)", month_label, start_date, end_date)

    with db.get_conn() as conn:
        # ── Funnel metrics ──────────────────────────────────────────────────────
        def count(status_clause: str, extra_where: str = "") -> int:
            row = conn.execute(
                f"SELECT COUNT(*) FROM permits WHERE customer_id=? {status_clause} {extra_where}",
                (CUSTOMER_ID,),
            ).fetchone()
            return row[0] if row else 0

        date_filter = f"AND created_at >= '{start_date}' AND created_at <= '{end_date}T23:59:59'"

        total_pulled    = count("AND status != 'template'", date_filter)
        total_excluded  = count("AND status='Excluded'", date_filter)
        total_sent      = count("AND status IN ('Sent','Drip Sent')", date_filter)
        total_engaged   = count("AND qr_scanned=1", date_filter)
        total_consults  = count("AND status='Consultation Scheduled'", date_filter)

        drip_sent       = count("AND status='Drip Sent'", date_filter)
        lob_errors      = count("AND status='Lob Error'", date_filter)

        # ── Exclusion reasons breakdown ─────────────────────────────────────────
        reason_rows = conn.execute(
            """SELECT exclude_reason, COUNT(*) as cnt
               FROM permits
               WHERE customer_id=? AND status='Excluded'
               AND created_at >= ? AND created_at <= ?
               GROUP BY exclude_reason
               ORDER BY cnt DESC""",
            (CUSTOMER_ID, start_date, end_date + "T23:59:59"),
        ).fetchall()

        # ── Top excluded contractors ────────────────────────────────────────────
        top_contractors = conn.execute(
            """SELECT rule_value, exclusion_count
               FROM exclusion_rules
               WHERE customer_id=? AND rule_type='Contractor' AND active=1
               ORDER BY exclusion_count DESC
               LIMIT 10""",
            (CUSTOMER_ID,),
        ).fetchall()

        # ── Auto-blocked contractors ────────────────────────────────────────────
        auto_blocked = conn.execute(
            """SELECT COUNT(*) FROM exclusion_rules
               WHERE customer_id=? AND rule_type='Contractor'
               AND auto_generated=1 AND active=1""",
            (CUSTOMER_ID,),
        ).fetchone()[0]

        # ── ZIP performance ─────────────────────────────────────────────────────
        zip_rows = conn.execute(
            """SELECT property_zip,
                      COUNT(*) as total,
                      SUM(CASE WHEN status IN ('Sent','Drip Sent') THEN 1 ELSE 0 END) as sent,
                      SUM(CASE WHEN qr_scanned=1 THEN 1 ELSE 0 END) as scanned,
                      SUM(CASE WHEN status='Consultation Scheduled' THEN 1 ELSE 0 END) as consults
               FROM permits
               WHERE customer_id=?
               AND created_at >= ? AND created_at <= ?
               GROUP BY property_zip
               ORDER BY sent DESC""",
            (CUSTOMER_ID, start_date, end_date + "T23:59:59"),
        ).fetchall()

        # ── Source breakdown ────────────────────────────────────────────────────
        source_rows = conn.execute(
            """SELECT source, COUNT(*) as cnt
               FROM permits
               WHERE customer_id=? AND created_at >= ? AND created_at <= ?
               GROUP BY source""",
            (CUSTOMER_ID, start_date, end_date + "T23:59:59"),
        ).fetchall()

        # ── New construction breakdown ──────────────────────────────────────────
        new_const_total = count("AND is_new_construction=1", date_filter)

    # ── Derived metrics ─────────────────────────────────────────────────────────
    total_cost        = total_sent * COST_PER_POSTCARD
    scan_rate         = f"{(total_engaged / total_sent * 100):.1f}%" if total_sent else "N/A"
    consult_rate      = f"{(total_consults / total_sent * 100):.1f}%" if total_sent else "N/A"
    cost_per_scan     = f"${(total_cost / total_engaged):.2f}" if total_engaged else "N/A"
    cost_per_consult  = f"${(total_cost / total_consults):.2f}" if total_consults else "N/A"

    # ── Build HTML ──────────────────────────────────────────────────────────────
    def metric_card(label: str, value) -> str:
        return f"""
        <td style="text-align:center;padding:16px 12px;border-right:1px solid #eee;">
          <div style="font-size:28px;font-weight:bold;color:#1a2744;">{value}</div>
          <div style="font-size:11px;color:#888;margin-top:4px;text-transform:uppercase;">{label}</div>
        </td>"""

    reasons_rows_html = ""
    for r in reason_rows:
        reasons_rows_html += f"""
        <tr>
          <td style="padding:6px 8px;font-size:12px;">{r['exclude_reason'] or 'No reason given'}</td>
          <td style="padding:6px 8px;font-size:12px;text-align:right;">{r['cnt']}</td>
        </tr>"""

    contractors_rows_html = ""
    for c in top_contractors:
        badge = " <span style='font-size:10px;color:#e8943a;'>AUTO-BLOCKED</span>" if c["exclusion_count"] >= config.AUTO_BLOCK_THRESHOLD else ""
        contractors_rows_html += f"""
        <tr>
          <td style="padding:6px 8px;font-size:12px;">{c['rule_value']}{badge}</td>
          <td style="padding:6px 8px;font-size:12px;text-align:right;">{c['exclusion_count']}</td>
        </tr>"""

    zip_rows_html = ""
    for z in zip_rows:
        z_scan_rate = f"{(z['scanned'] / z['sent'] * 100):.0f}%" if z['sent'] else "—"
        zip_rows_html += f"""
        <tr>
          <td style="padding:6px 8px;font-size:12px;">{z['property_zip']}</td>
          <td style="padding:6px 8px;font-size:12px;text-align:center;">{z['total']}</td>
          <td style="padding:6px 8px;font-size:12px;text-align:center;">{z['sent']}</td>
          <td style="padding:6px 8px;font-size:12px;text-align:center;">{z['scanned']}</td>
          <td style="padding:6px 8px;font-size:12px;text-align:center;">{z_scan_rate}</td>
          <td style="padding:6px 8px;font-size:12px;text-align:center;">{z['consults']}</td>
        </tr>"""

    source_html = ""
    for s in source_rows:
        source_html += f"<li style='font-size:12px;color:#555;'>{s['source']}: {s['cnt']} permit(s)</li>"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#333;max-width:750px;margin:0 auto;">

<div style="background:#1a2744;padding:24px;color:#fff;">
  <span style="color:#e8943a;font-size:20px;font-weight:bold;">PERMIT MINER</span>
  <span style="float:right;font-size:13px;color:#aaa;">{date.today()}</span><br>
  <span style="font-size:15px;">Monthly Report — {month_label}</span>
</div>

<!-- Funnel Metrics -->
<table width="100%" cellpadding="0" cellspacing="0"
       style="border-collapse:collapse;border:1px solid #eee;margin-top:0;">
  <tr>
    {metric_card("Permits Pulled", total_pulled)}
    {metric_card("Excluded", total_excluded)}
    {metric_card("Postcards Sent", total_sent)}
    {metric_card("QR Scans", total_engaged)}
    {metric_card("Consultations", total_consults)}
  </tr>
</table>

<!-- Conversion Rates -->
<div style="background:#f9f9f9;padding:16px 24px;border-bottom:1px solid #eee;">
  <span style="font-size:12px;color:#666;margin-right:24px;">Scan rate: <strong>{scan_rate}</strong></span>
  <span style="font-size:12px;color:#666;margin-right:24px;">Consult rate: <strong>{consult_rate}</strong></span>
  <span style="font-size:12px;color:#666;margin-right:24px;">Cost/scan: <strong>{cost_per_scan}</strong></span>
  <span style="font-size:12px;color:#666;margin-right:24px;">Cost/consult: <strong>{cost_per_consult}</strong></span>
  <span style="font-size:12px;color:#666;">Total spend: <strong>${total_cost:,.2f}</strong></span>
</div>

<!-- Additional stats -->
<div style="padding:12px 24px;font-size:12px;color:#666;background:#fff;border-bottom:1px solid #eee;">
  New construction: <strong>{new_const_total}</strong> &nbsp;·&nbsp;
  Drip sends: <strong>{drip_sent}</strong> &nbsp;·&nbsp;
  Lob errors: <strong>{lob_errors}</strong> &nbsp;·&nbsp;
  Auto-blocked contractors: <strong>{auto_blocked}</strong>
  <ul style="margin:8px 0 0 0;padding-left:20px;">{source_html}</ul>
</div>

<!-- Exclusion Learning -->
<div style="padding:16px 24px;">
  <h3 style="font-size:14px;color:#1a2744;margin:0 0 12px;">Exclusion Reasons</h3>
  {'<p style="font-size:12px;color:#999;">No exclusions this month.</p>' if not reason_rows else f"""
  <table width="100%" style="border-collapse:collapse;font-size:12px;">
    <thead><tr style="background:#f5f5f5;">
      <th style="padding:6px 8px;text-align:left;font-size:11px;color:#999;text-transform:uppercase;">Reason</th>
      <th style="padding:6px 8px;text-align:right;font-size:11px;color:#999;text-transform:uppercase;">Count</th>
    </tr></thead>
    <tbody>{reasons_rows_html}</tbody>
  </table>"""}
</div>

<!-- Top Excluded Contractors -->
<div style="padding:16px 24px;border-top:1px solid #eee;">
  <h3 style="font-size:14px;color:#1a2744;margin:0 0 12px;">Top Excluded Contractors (all-time)</h3>
  {'<p style="font-size:12px;color:#999;">No contractor exclusions yet.</p>' if not top_contractors else f"""
  <table width="100%" style="border-collapse:collapse;">
    <thead><tr style="background:#f5f5f5;">
      <th style="padding:6px 8px;text-align:left;font-size:11px;color:#999;text-transform:uppercase;">Contractor</th>
      <th style="padding:6px 8px;text-align:right;font-size:11px;color:#999;text-transform:uppercase;">Times Excluded</th>
    </tr></thead>
    <tbody>{contractors_rows_html}</tbody>
  </table>"""}
</div>

<!-- ZIP Performance -->
<div style="padding:16px 24px;border-top:1px solid #eee;">
  <h3 style="font-size:14px;color:#1a2744;margin:0 0 12px;">ZIP Code Performance</h3>
  {'<p style="font-size:12px;color:#999;">No data yet.</p>' if not zip_rows else f"""
  <table width="100%" style="border-collapse:collapse;">
    <thead><tr style="background:#f5f5f5;font-size:10px;color:#999;text-transform:uppercase;">
      <th style="padding:6px 8px;text-align:left;">ZIP</th>
      <th style="padding:6px 8px;text-align:center;">Pulled</th>
      <th style="padding:6px 8px;text-align:center;">Sent</th>
      <th style="padding:6px 8px;text-align:center;">Scanned</th>
      <th style="padding:6px 8px;text-align:center;">Scan%</th>
      <th style="padding:6px 8px;text-align:center;">Consults</th>
    </tr></thead>
    <tbody>{zip_rows_html}</tbody>
  </table>"""}
</div>

<div style="padding:16px 24px;font-size:11px;color:#999;border-top:1px solid #eee;">
  Permit Miner | Livewire &nbsp;·&nbsp; {month_label} &nbsp;·&nbsp;
  Postcard cost estimate based on ${COST_PER_POSTCARD:.2f}/piece (Lob 6x11 + postage)
</div>
</body></html>"""

    subject = f"Permit Miner Monthly Report — {month_label}"
    send_email(config.PREVIEW_RECIPIENTS, subject, html)
    log.info("Monthly report sent to %s", config.PREVIEW_RECIPIENTS)

    db.set_app_config_field("last_monthly_report", str(date.today()))
    log.info("=== Monthly Report complete ===")


if __name__ == "__main__":
    run()
