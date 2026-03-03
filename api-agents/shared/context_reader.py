"""context_reader.py — Read prior step reports for downstream agent context.

When a step has depends_on, the orchestrator collects reports from completed
dependency steps and passes them as the PRIOR_REPORTS env var.  This module
reads that env var or falls back to reading directly from Firestore.

Usage:
    from context_reader import read_prior_reports

    reports = read_prior_reports(org_id, run_id, step_id)
    # Inject into agent's LLM prompt as context
"""

from __future__ import annotations

import os

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


def read_prior_reports(
    org_id: str,
    run_id: str,
    step_id: str,
) -> str:
    """Read the aggregated prior reports for a step.

    Checks PRIOR_REPORTS env var first (set by orchestrator for efficiency).
    Falls back to reading the step doc's ``priorReports`` field from Firestore.

    Returns an empty string if no prior reports are available.
    """
    # Prefer env var (injected by orchestrator as Job env)
    env_reports = os.environ.get("PRIOR_REPORTS", "")
    if env_reports:
        return env_reports

    # Fallback: read from step doc in Firestore
    db = _get_db()
    doc = (
        db.collection("orgs").document(org_id)
        .collection("playbook_runs").document(run_id)
        .collection("steps").document(step_id)
        .get()
    )
    if not doc.exists:
        return ""
    return (doc.to_dict() or {}).get("priorReports", "")


def read_step_report(
    org_id: str,
    run_id: str,
    step_id: str,
) -> str | None:
    """Read a single step's completion report from Firestore."""
    db = _get_db()
    doc = (
        db.collection("orgs").document(org_id)
        .collection("playbook_runs").document(run_id)
        .collection("steps").document(step_id)
        .get()
    )
    if not doc.exists:
        return None
    return (doc.to_dict() or {}).get("report")
