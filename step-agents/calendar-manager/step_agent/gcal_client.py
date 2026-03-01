"""Google Calendar Client — Create events via the Google Calendar API v3.

Reads the Gmail OAuth token from Firestore org secrets (the token includes
the calendar.events scope) and creates events on the new hire's calendar.

Usage:
    from step_agent.gcal_client import create_event, batch_create_events

    event = create_event(
        org_id,
        summary="Welcome & Orientation",
        start="2025-04-01T09:00:00",
        end="2025-04-01T10:00:00",
        timezone="America/New_York",
        attendees=["jane@acme.com", "hr@acme.com"],
        description="Meet the team and get settled in.",
        location="Main Conference Room",
    )
"""

import requests

from step_agent.secrets_client import read_oauth_token

GCAL_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def create_event(
    org_id: str,
    summary: str,
    start: str,
    end: str,
    *,
    timezone: str = "America/New_York",
    attendees: list[str] | None = None,
    description: str = "",
    location: str = "",
) -> dict:
    """Create a single Google Calendar event."""
    token = read_oauth_token(org_id, "gmail")

    event_body: dict = {
        "summary": summary,
        "start": {"dateTime": start, "timeZone": timezone},
        "end": {"dateTime": end, "timeZone": timezone},
    }
    if description:
        event_body["description"] = description
    if location:
        event_body["location"] = location
    if attendees:
        event_body["attendees"] = [{"email": e} for e in attendees]

    resp = requests.post(
        GCAL_EVENTS_URL,
        headers={
            "Authorization": f"Bearer {token['accessToken']}",
            "Content-Type": "application/json",
        },
        json=event_body,
        params={"sendUpdates": "all"} if attendees else {},
        timeout=30,
    )
    resp.raise_for_status()

    data = resp.json()
    return {
        "id": data.get("id", ""),
        "htmlLink": data.get("htmlLink", ""),
        "status": data.get("status", ""),
    }


def batch_create_events(
    org_id: str,
    events: list[dict],
) -> list[dict]:
    """Create multiple calendar events. Raises on any failure."""
    results = []
    for evt in events:
        result = create_event(
            org_id,
            summary=evt["summary"],
            start=evt["start"],
            end=evt["end"],
            timezone=evt.get("timezone", "America/New_York"),
            attendees=evt.get("attendees"),
            description=evt.get("description", ""),
            location=evt.get("location", ""),
        )
        results.append(result)
    return results
