"""Send email with smtplib. Use a test/dummy account (see README)."""
from __future__ import annotations

import json
import re
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Dict, Optional

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$")


class EmailError(Exception):
    """Raised with a message that is safe to read out loud."""


def is_valid_email(address: str) -> bool:
    return bool(EMAIL_RE.match(address or ""))


def load_contacts(path: Path) -> Dict[str, str]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return {k.lower(): v for k, v in data.items() if is_valid_email(v)}
    except (OSError, ValueError, AttributeError):
        return {}


def resolve_recipient(spoken: str, contacts: Dict[str, str]) -> Optional[str]:
    """Contact name -> address, or a spoken/typed address if it is valid."""
    if not spoken:
        return None
    if spoken.lower() in contacts:
        return contacts[spoken.lower()]
    return spoken if is_valid_email(spoken) else None


def send_email(cfg, to: str, subject: str, body: str,
               smtp_factory: Optional[Callable] = None) -> None:
    msg = EmailMessage()
    msg["From"] = cfg.email_from or cfg.smtp_user
    msg["To"] = to
    msg["Subject"] = subject or "Message from your voice assistant"
    msg.set_content(body)
    try:
        if smtp_factory:
            server_cm = smtp_factory(cfg.smtp_host, cfg.smtp_port)
        elif cfg.smtp_port == 465:
            server_cm = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=15)
        else:
            server_cm = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15)
        with server_cm as server:
            if cfg.smtp_port != 465 and not smtp_factory:
                server.starttls()
            server.login(cfg.smtp_user, cfg.smtp_password)
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise EmailError("The email server rejected the login details.")
    except (smtplib.SMTPException, OSError):
        raise EmailError("I couldn't send the email. Please check the email settings and your connection.")
