import json
import logging

import requests

from utils.email import send_alert_email


logger = logging.getLogger(__name__)


def deliver_alert(channel: str, destination: str | None, subject: str, payload: dict) -> tuple[str, str | None]:
    if channel == "email":
        return ("sent", None) if send_alert_email(subject, f"<pre>{json.dumps(payload, indent=2)}</pre>", destination) else ("failed", "Email delivery failed or SMTP is not configured")
    if channel == "webhook":
        if not destination or not destination.startswith("https://"):
            return "failed", "Webhook destination must use HTTPS"
        try:
            response = requests.post(destination, json=payload, timeout=10)
            response.raise_for_status()
            return "sent", None
        except requests.RequestException as exc:
            logger.warning("webhook delivery failed", extra={"error_type": type(exc).__name__})
            return "failed", "Webhook delivery failed"
    if channel in {"slack", "teams"}:
        return "stubbed", None
    return "failed", "Unsupported alert channel"
