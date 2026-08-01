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
        logger.info("development email preview generated", extra={"subject": subject})
        _record_delivery(subject, receiver, "preview", "previewed")
        return True
    safe_url = escape(action_url, quote=True)
    body = responsive_email(subject, "Use the secure button below to continue. This link expires automatically.", safe_url, "Continue")
    sent = send_alert_email(subject, body, receiver)
    _record_delivery(subject, receiver, "resend" if settings.resend_api_key else "smtp", "sent" if sent else "failed")
    return sent


def _record_delivery(template: str, receiver: str, provider: str, status: str) -> None:
    try:
        get_db().table("email_deliveries").insert({"template": template[:120],
            "recipient_hash": hashlib.sha256(receiver.lower().encode()).hexdigest(),
            "provider": provider, "status": status}).execute()
    except Exception:
        logger.exception("email delivery audit failed", extra={"template": template[:120]})


TEMPLATES = {
    "welcome": ("Welcome to TokenWatch", "Your account is verified. You can now connect an SDK and protect your AI budget."),
    "verify_email": ("Verify your TokenWatch email", "Verify your address to activate your account."),
    "password_reset": ("Reset your TokenWatch password", "Use the secure link to reset your password."),
    "trial_ending": ("Your TokenWatch trial is ending", "Your trial is ending soon. Review your billing plan to avoid interruption."),
    "payment_failed": ("Payment failed for TokenWatch", "We could not process your latest payment. Update your billing details securely in the billing portal."),
    "invoice": ("Your TokenWatch invoice", "Your latest invoice is ready."),
    "subscription_active": ("Your TokenWatch subscription is active", "Your paid TokenWatch subscription is now active."),
    "subscription_cancelled": ("Your TokenWatch subscription was cancelled", "Your subscription has been cancelled. Your billing portal shows the effective date and available recovery options."),
    "invoice_paid": ("Your TokenWatch invoice was paid", "Your latest invoice has been paid successfully."),
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
    safe_link = escape(str(link), quote=True) if link and str(link).startswith("https://") else None
    body = responsive_email(subject, message, safe_link, "View securely")
    sent = send_alert_email(subject, body, receiver)
    try:
        get_db().table("email_deliveries").insert({"organization_id": organization_id, "user_id": user_id, "template": template,
            "recipient_hash": hashlib.sha256(receiver.lower().encode()).hexdigest(), "provider": "resend" if get_settings().resend_api_key else "smtp",
            "status": "sent" if sent else "failed"}).execute()
    except Exception:
        logger.exception("email delivery audit failed", extra={"template": template})
    return sent


def responsive_email(title: str, message: str, action_url: str | None = None, action_label: str = "Open TokenWatch") -> str:
    button = f'<a href="{action_url}" style="display:inline-block;background:#0f172a;color:#fff;text-decoration:none;padding:12px 20px;border-radius:8px;font-weight:600">{escape(action_label)}</a>' if action_url else ""
    return f'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f1f5f9;color:#0f172a;font-family:Arial,sans-serif"><table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td style="padding:24px 12px"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;margin:auto;background:#fff;border-radius:12px"><tr><td style="padding:32px"><p style="font-size:18px;font-weight:700;margin:0 0 24px">TokenWatch</p><h1 style="font-size:26px;line-height:1.25;margin:0 0 16px">{escape(title)}</h1><p style="font-size:16px;line-height:1.6;color:#475569;margin:0 0 24px">{escape(message)}</p>{button}<p style="font-size:12px;color:#64748b;margin:28px 0 0">This is a transactional service message from TokenWatch.</p></td></tr></table></td></tr></table></body></html>'''


def build_alert_email(alert_type: str, provider: str, current_val: float, limit_val: float, unit: str, period: str) -> tuple[str, str]:
    safe_provider, safe_type, safe_period = escape(provider.capitalize()), escape(alert_type.title()), escape(period)
    percent = round((current_val / limit_val) * 100, 1) if limit_val else 0
    status = "EXCEEDED" if percent >= 100 else "WARNING"
    subject = f"[TokenWatch] {status} — {safe_provider} {safe_type} Alert"
    body = f"<html><body><h1>TokenWatch Alert</h1><p><strong>{status}</strong>: {safe_provider} {safe_type}</p><p>Period: {safe_period}</p><p>Usage: {escape(unit)}{current_val:.4f} ({percent}% of limit)</p><p>Generated at {datetime.now().astimezone().isoformat()}</p></body></html>"
    return subject, body
