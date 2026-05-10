"""SparkPost email sender."""

from __future__ import annotations

import requests

SPARKPOST_API = "https://api.sparkpost.com/api/v1/transmissions"


class SparkPostError(RuntimeError):
    pass


def send_email(
    *,
    api_key: str,
    from_email: str,
    to: list[str],
    subject: str,
    html: str,
) -> None:
    """Send an HTML email via the SparkPost transmissions API."""
    payload = {
        "recipients": [{"address": addr} for addr in to],
        "content": {
            "from": from_email,
            "subject": subject,
            "html": html,
        },
    }
    resp = requests.post(
        SPARKPOST_API,
        json=payload,
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        timeout=30,
    )
    if not resp.ok:
        raise SparkPostError(f"SparkPost {resp.status_code}: {resp.text}")
