import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from config import get_settings

logger = logging.getLogger(__name__)

def send_alert_email(subject: str, body_html: str, receiver: str | None = None) -> bool:
    settings = get_settings()
    if not all([settings.smtp_host, settings.smtp_username, settings.smtp_password, settings.smtp_from_email, receiver]):
        logger.warning("alert email skipped because SMTP is not fully configured")
        return False


def send_action_email(subject: str, action_url: str, receiver: str) -> bool:
    safe_url = escape(action_url, quote=True)
    return send_alert_email(subject, f'<html><body><p>Use the secure link below to continue:</p><p><a href="{safe_url}">Continue</a></p><p>This link expires automatically.</p></body></html>', receiver)
    try:
        message = MIMEMultipart("alternative")
        message["Subject"], message["From"], message["To"] = subject, settings.smtp_from_email, receiver
        message.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as server:
            server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(settings.smtp_from_email, receiver, message.as_string())
        logger.info("alert email sent")
        return True
    except Exception:
        logger.exception("alert email failed")
        return False

def build_alert_email(alert_type: str, provider: str, current_val: float, limit_val: float, unit: str, period: str) -> tuple[str, str]:
    safe_provider, safe_type, safe_period = escape(provider.capitalize()), escape(alert_type.title()), escape(period)
    percent = round((current_val / limit_val) * 100, 1) if limit_val else 0
    status = "EXCEEDED" if percent >= 100 else "WARNING"
    subject = f"[TokenWatch] {status} — {safe_provider} {safe_type} Alert"
    body = f"<html><body><h1>TokenWatch Alert</h1><p><strong>{status}</strong>: {safe_provider} {safe_type}</p><p>Period: {safe_period}</p><p>Usage: {escape(unit)}{current_val:.4f} ({percent}% of limit)</p><p>Generated at {datetime.now().astimezone().isoformat()}</p></body></html>"
    return subject, body
