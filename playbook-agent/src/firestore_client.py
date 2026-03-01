"""Firestore Client — helpers for playbook run lifecycle events and status updates.

All paths follow: orgs/{orgId}/playbook_runs/{runId}/...
Uses Application Default Credentials (Workload Identity on GKE).
"""

import time

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
# Run document helpers
# ---------------------------------------------------------------------------


def read_run(org_id: str, run_id: str) -> dict | None:
    """Read the root playbook_runs document."""
    db = _get_db()
    doc = db.collection("orgs").document(org_id) \
        .collection("playbook_runs").document(run_id).get()
    return doc.to_dict() if doc.exists else None


def update_run_status(
    org_id: str,
    run_id: str,
    status: str,
    *,
    error: dict | None = None,
    summary: str | None = None,
    current_step_id: str | None = None,
) -> None:
    """Update the run document status + updatedAt."""
    db = _get_db()
    data: dict = {
        "status": status,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if error is not None:
        data["error"] = error
    if summary is not None:
        data["summary"] = summary
    if current_step_id is not None:
        data["currentStepId"] = current_step_id
    if status in ("completed", "failed", "aborted"):
        data["completedAt"] = firestore.SERVER_TIMESTAMP

    db.collection("orgs").document(org_id) \
        .collection("playbook_runs").document(run_id).update(data)


def update_run_heartbeat(org_id: str, run_id: str) -> None:
    """Update the lastHeartbeat timestamp (called every poll cycle by orchestrator)."""
    db = _get_db()
    db.collection("orgs").document(org_id) \
        .collection("playbook_runs").document(run_id) \
        .update({"lastHeartbeat": firestore.SERVER_TIMESTAMP})


# ---------------------------------------------------------------------------
# Step document helpers
# ---------------------------------------------------------------------------


def update_step_status(
    org_id: str,
    run_id: str,
    step_id: str,
    status: str,
    *,
    error: dict | None = None,
    result_summary: str | None = None,
    job_name: str | None = None,
) -> None:
    """Update a step document status."""
    db = _get_db()
    data: dict = {
        "status": status,
    }
    if error is not None:
        data["error"] = error
    if result_summary is not None:
        data["resultSummary"] = result_summary
    if job_name is not None:
        data["jobName"] = job_name
    if status == "running":
        data["startedAt"] = firestore.SERVER_TIMESTAMP
    if status == "paused":
        data["pausedAt"] = firestore.SERVER_TIMESTAMP
    if status in ("completed", "failed", "skipped"):
        data["completedAt"] = firestore.SERVER_TIMESTAMP

    db.collection("orgs").document(org_id) \
        .collection("playbook_runs").document(run_id) \
        .collection("steps").document(step_id).update(data)


def read_step_status(org_id: str, run_id: str, step_id: str) -> str | None:
    """Read a step's current status from Firestore."""
    db = _get_db()
    doc = db.collection("orgs").document(org_id) \
        .collection("playbook_runs").document(run_id) \
        .collection("steps").document(step_id).get()
    if not doc.exists:
        return None
    return (doc.to_dict() or {}).get("status")


# ---------------------------------------------------------------------------
# Event helpers (append-only log)
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
# Step initialisation
# ---------------------------------------------------------------------------


def initialize_step_docs(org_id: str, run_id: str, steps: list) -> None:
    """Create step documents in Firestore with 'pending' status.

    Uses .set() so documents are created fresh (not .update() which requires
    them to already exist).
    """
    from src.playbook_parser import StepDef

    db = _get_db()
    steps_ref = (
        db.collection("orgs").document(org_id)
        .collection("playbook_runs").document(run_id)
        .collection("steps")
    )

    for step in steps:
        if not isinstance(step, StepDef):
            continue
        steps_ref.document(step.id).set({
            "status": "pending",
            "title": step.title,
            "order": step.order,
            "agentImage": step.agent_image,
            "timeoutMinutes": step.timeout_minutes,
            "dependencies": step.dependencies,
            "createdAt": firestore.SERVER_TIMESTAMP,
        })


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------


def read_context(org_id: str, run_id: str) -> dict:
    """Read the run's hydrated context variables."""
    run = read_run(org_id, run_id)
    if run is None:
        return {}
    return run.get("context", {})


# ---------------------------------------------------------------------------
# Input polling (HITL)
# ---------------------------------------------------------------------------


def wait_for_input(
    org_id: str,
    run_id: str,
    step_id: str,
    question_id: str,
    timeout: int = 300,
    poll_interval: int = 5,
) -> dict | None:
    """Poll the inputs subcollection for a matching response.

    Returns the input document dict, or None on timeout.
    """
    db = _get_db()
    inputs_ref = db.collection("orgs").document(org_id) \
        .collection("playbook_runs").document(run_id) \
        .collection("inputs")

    deadline = time.time() + timeout
    while time.time() < deadline:
        # Check for abort
        run = read_run(org_id, run_id)
        if run and run.get("status") == "aborted":
            return {"type": "abort"}

        # Check for matching input
        query = inputs_ref \
            .where("stepId", "==", step_id) \
            .where("questionId", "==", question_id) \
            .limit(1)
        docs = list(query.stream())
        if docs:
            return docs[0].to_dict()

        time.sleep(poll_interval)

    return None


# ---------------------------------------------------------------------------
# Context fetchers (Issue 10 — hydration data sources)
# ---------------------------------------------------------------------------


def fetch_org_context(org_id: str) -> dict:
    """Fetch the org document fields (name, settings, etc.)."""
    db = _get_db()
    doc = db.collection("orgs").document(org_id).get()
    if not doc.exists:
        return {}
    data = doc.to_dict() or {}
    return {k: v for k, v in data.items() if k not in ("createdAt", "updatedAt")}


def fetch_role_members(org_id: str, role: str) -> list[dict]:
    """Fetch active org members with a given role."""
    db = _get_db()
    query = (
        db.collection("orgs").document(org_id).collection("members")
        .where("role", "==", role)
        .where("status", "==", "active")
    )
    results = []
    for doc in query.stream():
        d = doc.to_dict()
        results.append({
            "email": d.get("email", ""),
            "displayName": d.get("displayName", d.get("name", "")),
            "role": d.get("role", ""),
        })
    return results


def fetch_trigger_inputs(org_id: str, run_id: str) -> dict:
    """Read the triggerInputs from the run document."""
    run = read_run(org_id, run_id)
    if run is None:
        return {}
    return run.get("triggerInputs", {})


def build_hydration_context(
    org_id: str,
    run_id: str,
    variables: list,
) -> dict:
    """Build the nested context dict needed for variable resolution.

    Only fetches data sources actually referenced by the playbook's variables.
    Returns a dict like:
        {
            "org": {"name": "Acme Corp", ...},
            "run": {"context": {"new_hire_name": "Bob", ...}},
            "members": {"Engineering": [...], ...},
        }
    """
    from src.playbook_parser import VariableDef

    # Determine which source prefixes are needed
    sources = {v.source for v in variables if isinstance(v, VariableDef)}
    needs_org = any(s.startswith("org.") for s in sources)
    needs_run = any(s.startswith("run.") for s in sources)
    # Collect distinct roles needed from members.{role}.* sources
    member_roles: set[str] = set()
    for s in sources:
        if s.startswith("members."):
            parts = s.split(".", 2)
            if len(parts) >= 2:
                member_roles.add(parts[1])

    context: dict = {}

    if needs_org:
        context["org"] = fetch_org_context(org_id)

    if needs_run:
        context["run"] = {"context": fetch_trigger_inputs(org_id, run_id)}

    if member_roles:
        members_ctx: dict[str, list[dict]] = {}
        for role in member_roles:
            members_ctx[role] = fetch_role_members(org_id, role)
        context["members"] = members_ctx

    return context
