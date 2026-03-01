"""Jira Client — Create issues via the Jira Cloud REST API v3.

Reads the Jira OAuth token from Firestore org secrets, discovers the
Atlassian Cloud ID, and creates issues via the REST API.

Usage:
    from step_agent.jira_client import create_issue

    result = create_issue(
        org_id, project_key="HR",
        summary="Onboarding: Jane Doe",
        description="Complete onboarding checklist for new hire.",
    )
    # result = {'id': '...', 'key': 'HR-42', 'self': '...'}
"""

import requests

from step_agent.secrets_client import read_oauth_token

ATLASSIAN_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
JIRA_API_BASE = "https://api.atlassian.com/ex/jira"


def _get_cloud_id(access_token: str) -> str:
    """Discover the Atlassian Cloud ID for the authed user's Jira site."""
    resp = requests.get(
        ATLASSIAN_RESOURCES_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    resources = resp.json()
    if not resources:
        raise RuntimeError(
            "No accessible Jira sites found. "
            "Ensure the Jira OAuth token has the correct scopes."
        )
    return resources[0]["id"]


def create_issue(
    org_id: str,
    project_key: str,
    summary: str,
    description: str,
    *,
    issue_type: str = "Task",
    labels: list[str] | None = None,
) -> dict:
    """Create a Jira issue.

    Args:
        org_id: Organization ID (for reading OAuth token from Firestore).
        project_key: Jira project key (e.g. 'HR').
        summary: Issue summary / title.
        description: Issue description (plain text — converted to ADF).
        issue_type: Issue type name. Default 'Task'.
        labels: Optional list of labels.

    Returns:
        dict with 'id', 'key', 'self' from the Jira API response.

    Raises:
        ValueError: If Jira OAuth token is not configured.
        requests.HTTPError: If the Jira API returns an error.
    """
    token = read_oauth_token(org_id, "jira")
    access_token = token["accessToken"]

    cloud_id = _get_cloud_id(access_token)

    # Build Atlassian Document Format (ADF) for the description
    adf_description = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": description},
                ],
            },
        ],
    }

    fields: dict = {
        "project": {"key": project_key},
        "summary": summary,
        "description": adf_description,
        "issuetype": {"name": issue_type},
    }
    if labels:
        fields["labels"] = labels

    resp = requests.post(
        f"{JIRA_API_BASE}/{cloud_id}/rest/api/3/issue",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"fields": fields},
        timeout=30,
    )
    if not resp.ok:
        # Include response body for debugging (Jira returns detailed error messages)
        try:
            error_body = resp.json()
        except Exception:
            error_body = resp.text[:500]
        raise requests.HTTPError(
            f"{resp.status_code} {resp.reason} for url: {resp.url}\n"
            f"Response: {error_body}",
            response=resp,
        )

    data = resp.json()
    return {
        "id": data.get("id", ""),
        "key": data.get("key", ""),
        "self": data.get("self", ""),
    }
