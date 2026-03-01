"""Slack Client — Post messages via the Slack Web API.

Reads the Slack OAuth token from Firestore org secrets and uses the
chat.postMessage endpoint to send messages.

Usage:
    from step_agent.slack_client import post_message

    result = post_message(
        org_id, channel="#general",
        text="Welcome Jane Doe to the team!",
    )
    # result = {'ok': True, 'channel': 'C...', 'ts': '...'}
"""

import requests

from step_agent.secrets_client import read_oauth_token

SLACK_POST_URL = "https://slack.com/api/chat.postMessage"


def post_message(
    org_id: str,
    channel: str,
    text: str,
    *,
    blocks: list[dict] | None = None,
) -> dict:
    """Post a message to a Slack channel.

    Args:
        org_id: Organization ID (for reading OAuth token from Firestore).
        channel: Channel name (e.g. '#general') or channel ID.
        text: Fallback text for notifications and accessibility.
        blocks: Optional Block Kit blocks for rich formatting.

    Returns:
        dict with 'ok', 'channel', 'ts' from the Slack API response.

    Raises:
        ValueError: If Slack OAuth token is not configured.
        RuntimeError: If the Slack API returns ok=false.
    """
    token = read_oauth_token(org_id, "slack")

    payload: dict = {
        "channel": channel,
        "text": text,
    }
    if blocks:
        payload["blocks"] = blocks

    resp = requests.post(
        SLACK_POST_URL,
        headers={
            "Authorization": f"Bearer {token['accessToken']}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()

    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack API error: {data.get('error', 'unknown')}")

    return {
        "ok": True,
        "channel": data.get("channel", ""),
        "ts": data.get("ts", ""),
    }
