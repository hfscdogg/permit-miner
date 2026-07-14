"""
send_queued_preview.py — Email the Monday-style preview for everything
currently queued, outside the normal Monday schedule.

Used when permits are queued manually (e.g. released from a hold) so
Henry still gets one-click Exclude links before the next Tuesday send.

Run:  python -m pipeline.send_queued_preview
"""
import logging

import config
import db
from pipeline.mailer import send_email
from pipeline.monday_pull import build_preview_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

CUSTOMER_ID = "livewire"


def run():
    db.init_db()
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM permits WHERE customer_id=? "
            "AND status IN ('Queued', 'Drip Queued') "
            "ORDER BY status, property_zip",
            (CUSTOMER_ID,),
        ).fetchall()

    permits = [dict(r) for r in rows]
    log.info("%d permit(s) currently queued.", len(permits))

    html = build_preview_email(permits)
    subject = (
        f"Permit Miner — {len(permits)} permit"
        f"{'s' if len(permits) != 1 else ''} queued for next Tuesday send"
    )
    send_email(config.PREVIEW_RECIPIENTS, subject, html)
    log.info("Preview email sent to %s", config.PREVIEW_RECIPIENTS)


if __name__ == "__main__":
    run()
