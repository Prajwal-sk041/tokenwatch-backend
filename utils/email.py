import logging
import smtplib
import hashlib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from config import get_settings
from utils.database import get_db


logger = logging.getLogger(__name__)


def send_alert_email(subject: str, body_html: str, receiver: str | None = None) -> bool:
    settings = get_settings()
    if receiver and settings.resend_api_key and settings.smtp_from_email:
        try:
            import resend
            resend.api_key = settings.resend_api_key
            response = resend.Emails.send({"from": settings.smtp_from_email, "to": [receiver], "subject": subject, "html": body_html})
            logger.info("email delivery succeeded", extra={"delivery_channel": "resend", "message_id": response.get("id")})
            return True
        except Exception:
            logger.exception("email delivery failed; attempting fallback", extra={"delivery_channel": "resend"})
    if not all([settings.smtp_host, settings.smtp_username, settings.smtp_password, settings.smtp_from_email, receiver]):
        logger.warning("email delivery unavailable", extra={"delivery_channel": "resend_or_smtp"})
        return False
    try:
        message = MIMEMultipart("alternative")
        message["Subject"], message["From"], message["To"] = subject, settings.smtp_from_email, receiver
        message.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as server:
            server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(settings.smtp_from_email, receiver, message.as_string())
        logger.info("email delivery succeeded", extra={"delivery_channel": "smtp"})
        return True
    except Exception:
        logger.exception("email delivery failed", extra={"delivery_channel": "smtp"})
        return False


def send_action_email(subject: str, action_url: str, receiver: str) -> bool:
    settings = get_settings()
    if settings.email_preview_enabled and not settings.auth_cookie_secure:
        logger.warning("development email preview available", extra={"preview_url": action_url})
    safe_url = escape(action_url, quote=True)
    body = f'<html><body><p>Use the secure link below to continue:</p><p><a href="{safe_url}">Continue</a></p><p>This link expires automatically.</p></body></html>'
    return send_alert_email(subject, body, receiver)


TEMPLATES = {
    "trial_ending": ("Your TokenWatch trial is ending", "Your trial is ending soon. Review your billing plan to avoid interruption."),
    "payment_failed": ("Payment failed for TokenWatch", "We could not process your latest payment. Update your billing details securely in the billing portal."),
    "invoice": ("Your TokenWatch invoice", "Your latest invoice is ready."),
    "subscription_active": ("Your TokenWatch subscription is active", "Your paid TokenWatch subscription is now active."),
    "invite": ("You have been invited to TokenWatch", "You have received an organization invitation."),
}


def send_template_email(template: str, organization_id: str, *, receiver: str | None = None, context: dict | None = None) -> bool:
    if template not in TEMPLATES:
        raise ValueError("Unknown email template")
    if receiver is None:
        orgs = get_db().table("organizations").select("owner_user_id").eq("id", organization_id).limit(1).execute().data or []
        users = get_db().table("users").select("id,email").eq("id", orgs[0]["owner_user_id"]).limit(1).execute().data or [] if orgs else []
        receiver = users[0]["email"] if users else None
        user_id = users[0]["id"] if users else None
    else:
        user_id = None
    if not receiver:
        return False
    subject, message = TEMPLATES[template]
    safe_context = context or {}
    link = safe_context.get("invoice_url")
    body = f"<html><body><h1>{escape(subject)}</h1><p>{escape(message)}</p>"
    if link and str(link).startswith("https://"):
        body += f'<p><a href="{escape(str(link), quote=True)}">View securely</a></p>'
    body += "</body></html>"
    sent = send_alert_email(subject, body, receiver)
    try:
        get_db().table("email_deliveries").insert({"organization_id": organization_id, "user_id": user_id, "template": template,
            "recipient_hash": hashlib.sha256(receiver.lower().encode()).hexdigest(), "provider": "resend" if get_settings().resend_api_key else "smtp",
            "status": "sent" if sent else "failed"}).execute()
    except Exception:
        logger.exception("email delivery audit failed", extra={"template": template})
    return sent


def build_alert_email(alert_type: str, provider: str, current_val: float, limit_val: float, unit: str, period: str) -> tuple[str, str]:
    safe_provider, safe_type, safe_period = escape(provider.capitalize()), escape(alert_type.title()), escape(period)
    percent = round((current_val / limit_val) * 100, 1) if limit_val else 0
    status = "EXCEEDED" if percent >= 100 else "WARNING"
    subject = f"[TokenWatch] {status} — {safe_provider} {safe_type} Alert"
    body = f"<html><body><h1>TokenWatch Alert</h1><p><strong>{status}</strong>: {safe_provider} {safe_type}</p><p>Period: {safe_period}</p><p>Usage: {escape(unit)}{current_val:.4f} ({percent}% of limit)</p><p>Generated at {datetime.now().astimezone().isoformat()}</p></body></html>"
    return subject, body
