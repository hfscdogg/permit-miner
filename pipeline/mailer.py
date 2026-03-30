"""
mailer.py — Shared email-sending utility.
All pipeline modules import send_email() from here.
"""
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List

import config

log = logging.getLogger(__name__)


def send_email(to: List[str], subject: str, html_body: str) -> bool:
    """
    Send an HTML email via SMTP. Returns True on success.
    In test mode, logs the email instead of sending.
    """
    if not to:
        log.warning("send_email called with empty recipient list — skipping.")
        return False

    if config.MODE == "test" and not config.SMTP_USER:
        log.info("[TEST MODE] Would send email to %s — Subject: %s", to, subject)
        log.debug("Body preview: %s", html_body[:500])
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = config.SMTP_USER
    msg["To"]      = ", ".join(to)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASS)
            server.sendmail(config.SMTP_USER, to, msg.as_string())
        log.info("Email sent to %s — %s", to, subject)
        return True
    except Exception as e:
        log.error("Failed to send email to %s: %s", to, e)
        return False
