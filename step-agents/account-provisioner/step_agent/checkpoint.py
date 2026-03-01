"""Checkpoint helpers — save/load/clear checkpoint state in Firestore.

Checkpoints are stored on the step document as a `checkpoint` field.
This avoids filesystem dependency (emptyDir is ephemeral per pod).

Checkpoint data contains the execution phase, pending questionId, and any
accumulated state the agent needs to resume after a HITL pause.
"""

from __future__ import annotations

from step_agent.firestore_client import _get_db

from firebase_admin import firestore


def save_checkpoint(org_id: str, run_id: str, step_id: str, data: dict) -> None:
    """Write checkpoint data to the step document in Firestore."""
    db = _get_db()
    db.collection("orgs").document(org_id) \
        .collection("playbook_runs").document(run_id) \
        .collection("steps").document(step_id) \
        .update({"checkpoint": data, "updatedAt": firestore.SERVER_TIMESTAMP})


def load_checkpoint(org_id: str, run_id: str, step_id: str) -> dict | None:
    """Load checkpoint data from the step document. Returns None if no checkpoint."""
    db = _get_db()
    doc = db.collection("orgs").document(org_id) \
        .collection("playbook_runs").document(run_id) \
        .collection("steps").document(step_id).get()
    if not doc.exists:
        return None
    return (doc.to_dict() or {}).get("checkpoint")


def clear_checkpoint(org_id: str, run_id: str, step_id: str) -> None:
    """Remove checkpoint data from the step document (called on step completion)."""
    db = _get_db()
    db.collection("orgs").document(org_id) \
        .collection("playbook_runs").document(run_id) \
        .collection("steps").document(step_id) \
        .update({"checkpoint": firestore.DELETE_FIELD})
