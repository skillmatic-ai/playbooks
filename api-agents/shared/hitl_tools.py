"""HITL tools — ask_user and request_approval for API agents.

Checkpoint/resume model (same as step agents):
  - ask_user() and request_approval() write the Firestore event, save a
    checkpoint, mark the step as "paused", and terminate the pod (sys.exit(0)).
  - The Firebase Function onInputReceived detects the user's response and
    creates a new K8s Job with RESUME_THREAD_ID set.
  - The agent entrypoint detects RESUME_THREAD_ID, loads the checkpoint,
    reads the user's input, and resumes from the correct phase.

These functions never return — they always exit the process.
The user's answer is retrieved on resume via read_input() in firestore_client.
"""

from __future__ import annotations

import sys
import uuid

from checkpoint import save_checkpoint
from firestore_client import update_step_status, write_event


class InputTimeoutError(Exception):
    """Raised when polling for user input times out."""


class RunAbortedError(Exception):
    """Raised when the run is aborted while waiting for input."""


def ask_user(
    org_id: str,
    run_id: str,
    step_id: str,
    question: str,
    *,
    question_type: str = "free_text",
    options: list[str] | None = None,
    help_text: str | None = None,
    required: bool = True,
    checkpoint_data: dict | None = None,
) -> None:
    """Ask the user a question, checkpoint state, and terminate the pod.

    Writes a ``question`` event, saves a checkpoint, marks the step as
    ``paused``, and exits with code 0.  On resume, the entrypoint reads
    the checkpoint and the user's input, then continues.

    This function **never returns**.
    """
    question_id = str(uuid.uuid4())

    payload: dict = {
        "questionId": question_id,
        "question": question,
        "questionType": question_type,
        "required": required,
    }
    if options:
        payload["options"] = options
    if help_text:
        payload["helpText"] = help_text

    write_event(
        org_id, run_id, "question",
        step_id=step_id,
        payload=payload,
    )
    print(f"[hitl] Asked question: {question} (id={question_id})")

    save_checkpoint(org_id, run_id, step_id, {
        "phase": "waiting_for_answer",
        "questionId": question_id,
        "data": checkpoint_data or {},
    })
    print(f"[hitl] Checkpoint saved for question {question_id}")

    update_step_status(org_id, run_id, step_id, "paused")
    print(f"[hitl] Step {step_id} -> paused, terminating pod")
    sys.exit(0)


def request_approval(
    org_id: str,
    run_id: str,
    step_id: str,
    description: str,
    *,
    draft_content: str | None = None,
    risk_level: str = "medium",
    checkpoint_data: dict | None = None,
) -> None:
    """Request user approval, checkpoint state, and terminate the pod.

    Writes an ``approval_request`` event, saves a checkpoint, marks the
    step as ``paused``, and exits with code 0.

    This function **never returns**.
    """
    approval_id = str(uuid.uuid4())

    payload: dict = {
        "approvalId": approval_id,
        "description": description,
        "riskLevel": risk_level,
    }
    if draft_content:
        payload["draftContent"] = draft_content

    write_event(
        org_id, run_id, "approval_request",
        step_id=step_id,
        payload=payload,
    )
    print(f"[hitl] Requested approval: {description} (id={approval_id})")

    save_checkpoint(org_id, run_id, step_id, {
        "phase": "waiting_for_approval",
        "questionId": approval_id,
        "data": checkpoint_data or {},
    })
    print(f"[hitl] Checkpoint saved for approval {approval_id}")

    update_step_status(org_id, run_id, step_id, "paused")
    print(f"[hitl] Step {step_id} -> paused, terminating pod")
    sys.exit(0)
