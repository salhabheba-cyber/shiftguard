"""Minimal transactional email sender over SMTP (stdlib only — no new
dependency). Inert when not configured: logs the message instead of
sending it, so nothing crashes or silently fails before real SMTP
credentials (config.SMTP_USER/SMTP_PASSWORD) are set."""
import logging
import smtplib
from email.mime.text import MIMEText
import config

logger = logging.getLogger('shiftguard')

def send_email(to, subject, body_text):
    if not config.EMAIL_ENABLED:
        logger.warning(f"[email not configured] Would send to {to}: {subject}\n{body_text}")
        return False
    try:
        msg = MIMEText(body_text)
        msg['Subject'] = subject
        msg['From']    = config.SMTP_FROM
        msg['To']      = to
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.SMTP_FROM, [to], msg.as_string())
        return True
    except Exception as e:
        logger.error(f"Email send failed to {to}: {e}")
        return False
