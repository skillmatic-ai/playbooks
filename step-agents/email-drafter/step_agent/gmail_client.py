"""Gmail Client — Send emails via the Gmail REST API.

Reads the Gmail OAuth token from Firestore org secrets and uses the
Gmail API v1 to send emails.

Usage:
    from step_agent.gmail_client import send_email

    result = send_email(
        org_id, to="jane@acme.com",
        subject="Welcome to Acme Corp!",
        body="<h1>Welcome!</h1><p>We're excited to have you.</p>",
        cc=["manager@acme.com"],
    )
    # result = {'id': '...', 'threadId': '...'}
"""

import base64
from email.mime.text import MIMEText

import requests

from step_agent.secrets_client import read_oauth_token

GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def send_email(
    org_id: str,
    to: str,
    subject: str,
    body: str,
    *,
    cc: list[str] | None = None,
    content_type: str = "html",
) -> dict:
    """Send an email via the Gmail API.

    Args:
        org_id: Organization ID (for reading OAuth token from Firestore).
        to: Recipient email address.
        subject: Email subject line.
        body: Email body (HTML or plain text, based on content_type).
        cc: Optional list of CC recipients.
        content_type: 'html' or 'plain'. Default 'html'.

    Returns:
        dict with 'id' and 'threadId' from the Gmail API response.

    Raises:
        ValueError: If Gmail OAuth token is not configured.
        requests.HTTPError: If the Gmail API returns an error.
    """
    token = read_oauth_token(org_id, "gmail")

    mime = MIMEText(body, content_type)
    mime["to"] = to
    mime["subject"] = subject
    if cc:
        mime["cc"] = ", ".join(cc)

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")

    resp = requests.post(
        GMAIL_SEND_URL,
        headers={
            "Authorization": f"Bearer {token['accessToken']}",
            "Content-Type": "application/json",
        },
        json={"raw": raw},
        timeout=30,
    )
    resp.raise_for_status()

    data = resp.json()
    return {"id": data.get("id", ""), "threadId": data.get("threadId", "")}
