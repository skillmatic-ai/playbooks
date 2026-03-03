"""report_writer.py — Write step reports and artifacts to Firestore.

API agents call this module after completing their work to persist:
  - A markdown report summarising what was accomplished
  - An artifacts array listing resources created in external systems

The orchestrator reads these fields from the step doc and injects
them as context for downstream agents (see context_reader.py).

Usage:
    from report_writer import write_report

    await write_report(
        org_id, run_id, step_id,
        report_markdown="## Summary\nCreated PRD in Notion...",
        artifacts=[
            {"service": "notion", "type": "page", "title": "PRD v2",
             "url": "https://notion.so/...", "previewText": "Product requirements for..."},
        ],
    )
"""

from __future__ import annotations

import firebase_admin
from firebase_admin import firestore as fs

# ---------------------------------------------------------------------------
# Initialisation (module-level singleton)
# ---------------------------------------------------------------------------

_app: firebase_admin.App | None = None


def _get_db() -> fs.firestore.Client:
    global _app
    if _app is None:
        _app = firebase_admin.initialize_app()
    return fs.client(_app)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_report(
    org_id: str,
    run_id: str,
    step_id: str,
    report_markdown: str,
    artifacts: list[dict] | None = None,
) -> None:
    """Write the completion report and artifacts to the step document.

    Args:
        report_markdown: Markdown text summarising the step's output.
        artifacts: List of artifact dicts, each with at minimum:
            - service (str): e.g. "notion", "zendesk", "github"
            - type (str): e.g. "page", "ticket", "issue", "document"
            - title (str): Human-readable title
            - url (str): Deep link to the resource in the external service
            Optional: previewText (str), metadata (dict)
    """
    db = _get_db()
    data: dict = {
        "report": report_markdown,
        "updatedAt": fs.SERVER_TIMESTAMP,
    }
    if artifacts:
        data["artifacts"] = artifacts

    db.collection("orgs").document(org_id) \
        .collection("playbook_runs").document(run_id) \
        .collection("steps").document(step_id) \
        .update(data)


def emit_artifact_events(
    org_id: str,
    run_id: str,
    step_id: str,
    artifacts: list[dict],
) -> None:
    """Emit an artifact_ready event for each artifact (shows in chat thread)."""
    db = _get_db()
    events_ref = (
        db.collection("orgs").document(org_id)
        .collection("playbook_runs").document(run_id)
        .collection("events")
    )

    for artifact in artifacts:
        events_ref.add({
            "type": "artifact_ready",
            "stepId": step_id,
            "timestamp": fs.SERVER_TIMESTAMP,
            "payload": {
                "service": artifact.get("service", "external"),
                "type": artifact.get("type", "resource"),
                "title": artifact.get("title", "Untitled"),
                "url": artifact.get("url", ""),
                "previewText": artifact.get("previewText", ""),
            },
        })
