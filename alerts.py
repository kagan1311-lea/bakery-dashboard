"""Email the site maintainer when the ask box hits an error.

Off unless ALERT_EMAIL and the SMTP_* variables are set (see .env.example), so the app works the
same without them. At most one email per error type every THROTTLE_S, so an outage doesn't flood the
inbox. The email never carries a secret: known secret values and connection strings are masked.
"""

import logging
import os
import re
import smtplib
import time
from datetime import datetime
from email.message import EmailMessage

THROTTLE_S = 15 * 60
REQUIRED = ("ALERT_EMAIL", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")
SECRET_VARS = ("ANTHROPIC_API_KEY", "DATABASE_URL", "DATABASE_ADMIN_URL", "TEST_DATABASE_URL", "SMTP_PASSWORD")
SECRET_PATTERNS = (re.compile(r"postgres(?:ql)?://\S+"), re.compile(r"sk-ant-[\w-]+"))

log = logging.getLogger("bakery.alerts")
_last_sent = {}  # error type -> time.monotonic() of the last email (per process)


def configured():
    return all(os.environ.get(name) for name in REQUIRED)


def mask(text):
    for name in SECRET_VARS:
        if value := os.environ.get(name):
            text = text.replace(value, "[hidden]")
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[hidden]", text)
    return text


def send_error_alert(error_type, question, detail, now=None):
    """Email the maintainer about one ask-box error. Returns True if an email was sent."""
    if not configured():
        return False
    now = time.monotonic() if now is None else now
    if error_type in _last_sent and now - _last_sent[error_type] < THROTTLE_S:
        return False

    msg = EmailMessage()
    msg["Subject"] = f"[bakery-dashboard] ask box error: {error_type}"
    msg["From"] = os.environ["SMTP_USER"]
    msg["To"] = os.environ["ALERT_EMAIL"]
    msg.set_content(
        f"Time: {datetime.now().isoformat(timespec='seconds')}\n"
        f"Error: {error_type}\n"
        f"Question: {mask(question)[:200]}\n"
        f"Detail: {mask(detail)[:300]}\n\n"
        f"Next emails for {error_type} are held for {THROTTLE_S // 60} minutes. "
        "Full details are in the Railway logs (logger bakery.ask)."
    )
    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587")), timeout=10) as smtp:
            smtp.starttls()
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        log.warning("could not send alert email (%s)", type(e).__name__)
        return False
    _last_sent[error_type] = now
    return True
