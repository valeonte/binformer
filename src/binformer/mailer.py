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
    inline_images: list[dict] | None = None,
) -> None:
    """Send an HTML email via the SparkPost transmissions API.

    inline_images entries: {"name": str, "type": "image/png", "data": "<base64>"}
    Reference in HTML with src="cid:<name>".
    """
    content: dict = {
        "from": from_email,
        "subject": subject,
        "html": html,
    }
    if inline_images:
        content["inline_images"] = inline_images
    payload = {
        "recipients": [{"address": addr} for addr in to],
        "content": content,
    }
    resp = requests.post(
        SPARKPOST_API,
        json=payload,
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        timeout=30,
    )
    if not resp.ok:
        raise SparkPostError(f"SparkPost {resp.status_code}: {resp.text}")
