"""Send e-mail through SMTP when configured; otherwise log the message.

Without ``MAIL_SERVER`` nothing leaves the machine: the message (including any
password-reset link) is written to the application log so a developer can
copy it during a demo.
"""
import smtplib
from email.message import EmailMessage

from flask import current_app


def send_mail(to: str, subject: str, body: str) -> bool:
    """Return True if the message was handed to an SMTP server."""
    cfg = current_app.config
    server = cfg.get("MAIL_SERVER")
    if not server:
        current_app.logger.warning("MAIL NOT CONFIGURED - would send to %s\nSubject: %s\n%s",
                                   to, subject, body)
        return False
    message = EmailMessage()
    message["From"] = cfg["MAIL_FROM"]
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(server, cfg["MAIL_PORT"], timeout=15) as smtp:
            if cfg["MAIL_USE_TLS"]:
                smtp.starttls()
            if cfg.get("MAIL_USERNAME"):
                smtp.login(cfg["MAIL_USERNAME"], cfg.get("MAIL_PASSWORD", ""))
            smtp.send_message(message)
        return True
    except (OSError, smtplib.SMTPException):
        current_app.logger.exception("Could not send e-mail to %s", to)
        return False
