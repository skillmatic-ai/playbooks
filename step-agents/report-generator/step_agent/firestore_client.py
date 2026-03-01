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
    """Read a single input document by questionId or approvalId.

    Called on resume — the input document should already exist because the
    Firebase Function onInputReceived only creates a resume Job after the
    user submits their response.

    The app writes questionId for question answers and approvalId for
    approval decisions.  The checkpoint always stores the ID under the
    ``questionId`` key, so we search both Firestore fields.

    Returns the input document dict, or None if not found.
    """
    db = _get_db()
    inputs_ref = db.collection("orgs").document(org_id) \
        .collection("playbook_runs").document(run_id) \
        .collection("inputs")

    # Try questionId first (question answers)
    docs = list(inputs_ref.where("questionId", "==", question_id).limit(1).stream())
    if docs:
        return docs[0].to_dict()

    # Fall back to approvalId (approval decisions)
    docs = list(inputs_ref.where("approvalId", "==", question_id).limit(1).stream())
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


# ---------------------------------------------------------------------------
# Cross-step data reading (for report/aggregation agents)
# ---------------------------------------------------------------------------


def read_all_step_results(org_id: str, run_id: str) -> list[dict]:
    """Read all step documents from the run for cross-step data aggregation.

    Returns a list of step document dicts with id, title, status, resultSummary, etc.
    """
    db = _get_db()
    steps_ref = (
        db.collection("orgs").document(org_id)
        .collection("playbook_runs").document(run_id)
        .collection("steps")
    )
    results = []
    for doc in steps_ref.order_by("order").stream():
        data = doc.to_dict() or {}
        data["id"] = doc.id
        results.append(data)
    return results


def read_all_files(org_id: str, run_id: str) -> list[dict]:
    """Read all file documents from the run's files subcollection.

    Returns a list of file metadata dicts with name, stepId, storagePath, etc.
    """
    db = _get_db()
    files_ref = (
        db.collection("orgs").document(org_id)
        .collection("playbook_runs").document(run_id)
        .collection("files")
    )
    results = []
    for doc in files_ref.stream():
        data = doc.to_dict() or {}
        data["fileId"] = doc.id
        results.append(data)
    return results
