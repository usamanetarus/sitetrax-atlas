"""Resend email sender — a single HTTPS POST via httpx (no SDK).

Configured by env: RESEND_API_KEY, ALERT_EMAIL_FROM (defaults to Resend's onboarding
sender, which can email your own verified address with no domain setup).
"""

import os
import logging

import httpx

logger = logging.getLogger("sitetrax")

_API = "https://api.resend.com/emails"
_TIMEOUT = 8.0


def send_email(to: str, subject: str, html: str) -> bool:
    """Send one email via Resend. Returns True on success; raises on HTTP error."""
    key = os.environ.get("RESEND_API_KEY", "")
    sender = os.environ.get("ALERT_EMAIL_FROM", "onboarding@resend.dev")
    if not key:
        logger.warning("RESEND_API_KEY unset — cannot send email")
        return False

    resp = httpx.post(
        _API,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"from": sender, "to": [to], "subject": subject, "html": html},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    logger.info("Alert email sent to %s", to)
    return True
