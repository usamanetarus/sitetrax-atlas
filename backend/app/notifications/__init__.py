"""Notification dispatch — pluggable, selected by EMAIL_PROVIDER.

Default `none` logs only (no send), so the demo/tests never depend on email.
Mirrors the `app/data` and `app/monitoring` selector pattern.
"""

import html as _html
import os
import logging

logger = logging.getLogger("sitetrax")


def notify_alert(alert: dict, recipient: str | None = None) -> bool:
    """Dispatch a fired alert as an email. Returns True if actually sent. Never raises."""
    provider = os.environ.get("EMAIL_PROVIDER", "none").lower()
    to = recipient or os.environ.get("ALERT_EMAIL_TO", "")
    subject = f"[SiteTrax] {_html.escape(alert.get('trigger', 'Monitoring alert'))}"
    html_body = _format_html(alert)

    if provider == "resend":
        if not to:
            logger.warning("Alert fired but no recipient set (ALERT_EMAIL_TO) — skipping email")
            return False
        try:
            from .resend_sender import send_email
            return send_email(to=to, subject=subject, html=html_body)
        except Exception as e:  # delivery must never break the request/eval path
            logger.warning("Email send failed (%s) — alert still recorded", e)
            return False

    # "none" or unknown → log only
    logger.info("[alert] (email disabled) would notify %s: %s", to or "(no recipient)", subject)
    return False


def _format_html(alert: dict) -> str:
    trigger = _html.escape(str(alert.get('trigger', '')))
    rule_id = _html.escape(str(alert.get('rule_id', '')))
    template = _html.escape(str(alert.get('template', '')))
    timestamp = _html.escape(str(alert.get('timestamp', '')))
    return (
        "<h2>SiteTrax Alert</h2>"
        f"<p><strong>{trigger}</strong></p>"
        "<ul>"
        f"<li>Rule: {rule_id}</li>"
        f"<li>Template: {template}</li>"
        f"<li>Time: {timestamp}</li>"
        "</ul>"
    )
