import json
import logging
import ipaddress
import socket
from urllib.parse import urlparse

import requests

from utils.email import send_alert_email


logger = logging.getLogger(__name__)


def _is_public_https_url(destination: str) -> bool:
    parsed = urlparse(destination)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return False
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
        return bool(addresses) and all(ipaddress.ip_address(address).is_global for address in addresses)
    except (OSError, ValueError):
        return False


def deliver_alert(channel: str, destination: str | None, subject: str, payload: dict) -> tuple[str, str | None]:
    if channel == "email":
        return ("sent", None) if send_alert_email(subject, f"<pre>{json.dumps(payload, indent=2)}</pre>", destination) else ("failed", "Email delivery failed or SMTP is not configured")
    if channel == "webhook":
        if not destination or not _is_public_https_url(destination):
            return "failed", "Webhook destination must be a public HTTPS endpoint"
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
