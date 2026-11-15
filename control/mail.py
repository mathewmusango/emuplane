#!/usr/bin/env python3
"""Outbound mail, for the one message this control has to send.

Standard library only — `smtplib` plus `email.message` — because the runtime
image carries no third-party packages and this is one short message.

Settings are `EP_MAIL_*` (see `.env.example`); `EP_MAIL_HOST` empty means mail is
off. Credentials are read from the environment and never logged: a failure is
reported by its stage and the SMTP status code, not by echoing the exchange.

The message is `multipart/alternative` (plain text plus a branded HTML part) and
the product mark is embedded as `multipart/related` with a `cid:` — a remote
`<img>` would be blocked by most clients and would point at a host the recipient
cannot reach.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage


class MailError(RuntimeError):
    """Sending failed. The message names the stage, never the credential."""


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def host() -> str:
    return _env("EP_MAIL_HOST")


def configured() -> bool:
    """True when a relay is configured well enough to attempt a send."""
    return bool(host() and _env("EP_MAIL_FROM"))


def port() -> int:
    try:
        return int(_env("EP_MAIL_PORT", "587") or 587)
    except ValueError:
        return 587


def security() -> str:
    """`starttls` (587, the default), `ssl` (465), or `none` (a local relay)."""
    return (_env("EP_MAIL_SECURITY", "starttls") or "starttls").lower()


def build(
    to: str,
    subject: str,
    body: str,
    html_body: str = "",
    logo: str = "",
) -> EmailMessage:
    """Assemble the message without sending it (the tests inspect this)."""
    message = EmailMessage()
    message["From"] = _env("EP_MAIL_FROM")
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    if not html_body:
        return message
    message.add_alternative(html_body, subtype="html")
    if logo and os.path.isfile(logo):
        try:
            with open(logo, "rb") as handle:
                data = handle.read()
            message.get_payload()[-1].add_related(
                data,
                maintype="image",
                subtype="png",
                cid="<emuplane-logo>",
                filename="emuplane.png",
            )
        except (OSError, ValueError):
            pass  # a missing logo must never stop the mail
    return message


def deliver(message: EmailMessage) -> None:
    """Hand a built message to the relay, or raise MailError."""
    mode = security()
    user = _env("EP_MAIL_USER")
    password = _env("EP_MAIL_PASSWORD")
    context = ssl.create_default_context()

    try:
        if mode == "ssl":
            client = smtplib.SMTP_SSL(host(), port(), timeout=15, context=context)
        else:
            client = smtplib.SMTP(host(), port(), timeout=15)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailError(f"cannot reach the relay: {type(exc).__name__}") from exc

    try:
        client.ehlo()
        if mode == "starttls":
            client.starttls(context=context)
            client.ehlo()
        if user:
            client.login(user, password)
        client.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise MailError(
            f"the relay refused the credentials ({exc.smtp_code})"
        ) from exc
    except (OSError, smtplib.SMTPException) as exc:
        raise MailError(f"the relay refused the message: {exc}") from exc
    finally:
        try:
            client.quit()
        except (OSError, smtplib.SMTPException):
            pass


def send(
    to: str,
    subject: str,
    body: str,
    html_body: str = "",
    logo: str = "",
) -> None:
    """Build and deliver one message, or raise MailError."""
    if not configured():
        raise MailError("no relay is configured")
    deliver(build(to, subject, body, html_body, logo))
