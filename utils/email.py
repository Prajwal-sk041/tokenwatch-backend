import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

GMAIL_SENDER       = os.getenv("GMAIL_SENDER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
ALERT_RECEIVER     = os.getenv("ALERT_RECEIVER")


def send_alert_email(subject: str, body_html: str, receiver: str = None) -> bool:
    to = receiver or ALERT_RECEIVER
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"TokenWatch Alerts <{GMAIL_SENDER}>"
        msg["To"]      = to
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_SENDER, to, msg.as_string())

        print(f"[EMAIL] ✅ Sent to {to}: {subject}")
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] ❌ {e}")
        return False


def build_alert_email(
    alert_type: str,
    provider: str,
    current_val: float,
    limit_val: float,
    unit: str,
    period: str
) -> tuple[str, str]:
    now    = datetime.now().strftime("%d %b %Y, %I:%M %p")
    pct    = round((current_val / limit_val) * 100, 1) if limit_val else 0
    color  = "#ef4444" if pct >= 100 else "#f59e0b"
    status = "EXCEEDED 🚨" if pct >= 100 else "WARNING ⚠️"
    icon   = "💰" if unit == "$" else "🔢"

    subject = f"[TokenWatch] {status} — {provider.capitalize()} {alert_type} Alert"

    body = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0;padding:0;background:#f8fafc;font-family:Inter,Arial,sans-serif;">
      <div style="max-width:580px;margin:32px auto;background:#f8fafc;padding:0 16px;">

        <!-- Header -->
        <div style="background:#1e293b;border-radius:16px 16px 0 0;padding:28px 32px;">
          <h1 style="color:#fff;margin:0;font-size:22px;font-weight:700;">🔐 TokenWatch Alert</h1>
          <p style="color:#94a3b8;margin:6px 0 0;font-size:13px;">Automated usage monitoring system</p>
        </div>

        <!-- Body -->
        <div style="background:#fff;border-radius:0 0 16px 16px;padding:28px 32px;border:1px solid #e2e8f0;border-top:none;">

          <!-- Status Banner -->
          <div style="background:{color}18;border:1.5px solid {color};border-radius:12px;padding:16px 20px;margin-bottom:24px;">
            <p style="margin:0;font-size:20px;font-weight:700;color:{color};">{status}</p>
            <p style="margin:6px 0 0;color:#475569;font-size:14px;">
              {icon} <strong>{provider.capitalize()}</strong> — {alert_type.replace("_", " ").title()} limit
              {'exceeded' if pct >= 100 else 'approaching'}
            </p>
          </div>

          <!-- Details Table -->
          <table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:20px;">
            <tr style="background:#f8fafc;">
              <td style="padding:11px 14px;color:#64748b;border-radius:8px 0 0 8px;width:40%;">Provider</td>
              <td style="padding:11px 14px;font-weight:600;color:#1e293b;">{provider.capitalize()}</td>
            </tr>
            <tr>
              <td style="padding:11px 14px;color:#64748b;">Alert Type</td>
              <td style="padding:11px 14px;font-weight:600;color:#1e293b;">{alert_type.replace("_", " ").title()}</td>
            </tr>
            <tr style="background:#f8fafc;">
              <td style="padding:11px 14px;color:#64748b;">Period</td>
              <td style="padding:11px 14px;font-weight:600;color:#1e293b;">{period}</td>
            </tr>
            <tr>
              <td style="padding:11px 14px;color:#64748b;">Current Usage</td>
              <td style="padding:11px 14px;font-weight:700;color:{color};">
                {unit}{current_val:.4f} &nbsp;({pct}% of limit)
              </td>
            </tr>
            <tr style="background:#f8fafc;">
              <td style="padding:11px 14px;color:#64748b;">Your Limit</td>
              <td style="padding:11px 14px;font-weight:600;color:#1e293b;">{unit}{limit_val:.4f}</td>
            </tr>
          </table>

          <!-- Progress Bar -->
          <div style="margin-bottom:20px;">
            <div style="background:#f1f5f9;border-radius:99px;height:10px;overflow:hidden;">
              <div style="background:{color};height:10px;width:{min(pct, 100)}%;border-radius:99px;transition:width 0.3s;"></div>
            </div>
            <p style="margin:6px 0 0;font-size:12px;color:#94a3b8;text-align:right;">{pct}% used</p>
          </div>

          <!-- Timestamp -->
          <div style="padding:12px 16px;background:#f1f5f9;border-radius:10px;font-size:12px;color:#64748b;">
            🕐 Alert triggered at <strong>{now} IST</strong>
          </div>

          <!-- Footer -->
          <p style="margin-top:24px;font-size:12px;color:#94a3b8;text-align:center;line-height:1.6;">
            You are receiving this because you configured alerts in TokenWatch.<br/>
            Visit your dashboard to manage alert rules.
          </p>
        </div>
      </div>
    </body>
    </html>
    """
    return subject, body