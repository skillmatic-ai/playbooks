"""Firestore Client — step agent helpers for status updates, events, and input reading.

All paths follow: orgs/{orgId}/playbook_runs/{runId}/...
Uses Application Default Credentials (Workload Identity on GKE).
"""

from __future__ import annotations

import firebase_admin
from firebase_admin import firestore

# ---------------------------------------------------------------------------
# Initialisation (module-level singleton)
# ---------------------------------------------------------------------------

_app: firebase_admin.App | None = None


def _get_db() -> firestore.firestore.Client:
    global _app
    if _app is None:
        _app = firebase_admin.initialize_app()
    return firestore.client(_app)


# ---------------------------------------------------------------------------
# Step status
# ---------------------------------------------------------------------------


def update_step_status(
    org_id: str,
    run_id: str,
    step_id: str,
    status: str,
    *,
    error: dict | None = None,
    result_summary: str | None = None,
) -> None:
    """Update a step document's status and timestamps."""
    db = _get_db()
    data: dict = {"status": status}

    if error is not None:
        data["error"] = error
    if result_summary is not None:
        data["resultSummary"] = result_summary
    if status == "running":
        data["startedAt"] = firestore.SERVER_TIMESTAMP
    if status == "paused":
        data["pausedAt"] = firestore.SERVER_TIMESTAMP
    if status in ("completed", "failed", "skipped"):
        data["completedAt"] = firestore.SERVER_TIMESTAMP

    db.collection("orgs").document(org_id) \
        .collection("playbook_runs").document(run_id) \
        .collection("steps").document(step_id).update(data)


# ---------------------------------------------------------------------------
# Events (append-only log)
# ---------------------------------------------------------------------------


def write_event(
    org_id: str,
    run_id: str,
    event_type: str,
    *,
    step_id: str | None = None,
    payload: dict | None = None,
) -> str:
    """Append an event to the run's events subcollection. Returns the event ID."""
    db = _get_db()
    data = {
        "type": event_type,
        "stepId": step_id,
        "timestamp": firestore.SERVER_TIMESTAMP,
        "payload": payload or {},
    }
    _, doc_ref = db.collection("orgs").document(org_id) \
        .collection("playbook_runs").document(run_id) \
        .collection("events").add(data)
    return doc_ref.id


# ---------------------------------------------------------------------------
# Context reading
# ---------------------------------------------------------------------------


def read_run_context(org_id: str, run_id: str) -> dict:
    """Read the hydrated context variables from the run document."""
    db = _get_db()
    doc = db.collection("orgs").document(org_id) \
        .collection("playbook_runs").document(run_id).get()
    if not doc.exists:
        return {}
    run_data = doc.to_dict() or {}
    return run_data.get("context", {})


# ---------------------------------------------------------------------------
# HITL input reading (checkpoint/resume model)
# ---------------------------------------------------------------------------


def read_input(
    org_id: str,
    run_id: str,
    question_id: str,
) -> dict | None:
    """Read a single input document by questionId (direct read, no polling).

    Called on resume — the input document should already exist because the
    Firebase Function onInputReceived only creates a resume Job after the
    user submits their response.

    Returns the input document dict, or None if not found.
    """
    db = _get_db()
    inputs_ref = db.collection("orgs").document(org_id) \
        .collection("playbook_runs").document(run_id) \
        .collection("inputs")

    query = inputs_ref \
        .where("questionId", "==", question_id) \
        .limit(1)
    docs = list(query.stream())
    if docs:
        return docs[0].to_dict()
    return None


def read_run_status(org_id: str, run_id: str) -> str | None:
    """Read the run's current status."""
    db = _get_db()
    doc = db.collection("orgs").document(org_id) \
        .collection("playbook_runs").document(run_id).get()
    if not doc.exists:
        return None
    return (doc.to_dict() or {}).get("status")
