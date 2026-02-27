"""HITL tools — ask_user and request_approval for step agents.

Issue 15 checkpoint/resume model:
  - ask_user() and request_approval() write the Firestore event, save a
    checkpoint to the shared PVC, mark the step as "paused", and terminate
    the pod (sys.exit(0)).
  - The Firebase Function onInputReceived detects the user's response and
    creates a new K8s Job with RESUME_THREAD_ID set.
  - The step agent entrypoint detects RESUME_THREAD_ID, loads the checkpoint,
    reads the user's input, and resumes from the correct phase.

The functions in this module never return — they always exit the process.
The user's answer is retrieved on resume via read_input() in firestore_client.
"""

from __future__ import annotations

import sys
import uuid

from step_agent.checkpoint import save_checkpoint
from step_agent.firestore_client import update_step_status, write_event


class InputTimeoutError(Exception):
    """Raised when polling for user input times out (legacy — kept for resume error handling)."""


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

    Writes a ``question`` event to Firestore, saves a checkpoint file, marks
    the step as ``paused``, and exits with code 0.  The pod terminates cleanly
    and the K8s Job succeeds.

    On resume the entrypoint reads the checkpoint and the user's input from
    Firestore, then continues from the appropriate phase.

    Args:
        question_type: One of ``free_text``, ``single_select``, ``multi_select``.
        options: Choice options (required for select types).
        help_text: Optional contextual help shown alongside the question.
        required: Whether the user must answer before proceeding.
        checkpoint_data: Arbitrary dict of accumulated state to persist across
            the pause.  Restored on resume via ``load_checkpoint()``.

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

    # Write question event
    write_event(
        org_id, run_id, "question",
        step_id=step_id,
        payload=payload,
    )
    print(f"[hitl] Asked question: {question} (id={question_id})")

    # Save checkpoint
    save_checkpoint(step_id, {
        "phase": "waiting_for_answer",
        "questionId": question_id,
        "data": checkpoint_data or {},
    })
    print(f"[hitl] Checkpoint saved for question {question_id}")

    # Mark step as paused and terminate pod
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

    Writes an ``approval_request`` event to Firestore, saves a checkpoint,
    marks the step as ``paused``, and exits with code 0.

    On resume the entrypoint reads the checkpoint and the approval decision
    from Firestore, then continues from the appropriate phase.

    Args:
        description: What is being requested.
        draft_content: The content/action being proposed (shown to user).
        risk_level: One of ``low``, ``medium``, ``high``.
        checkpoint_data: Arbitrary dict of accumulated state.

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

    # Write approval_request event
    write_event(
        org_id, run_id, "approval_request",
        step_id=step_id,
        payload=payload,
    )
    print(f"[hitl] Requested approval: {description} (id={approval_id})")

    # Save checkpoint
    save_checkpoint(step_id, {
        "phase": "waiting_for_approval",
        "questionId": approval_id,
        "data": checkpoint_data or {},
    })
    print(f"[hitl] Checkpoint saved for approval {approval_id}")

    # Mark step as paused and terminate pod
    update_step_status(org_id, run_id, step_id, "paused")
    print(f"[hitl] Step {step_id} -> paused, terminating pod")
    sys.exit(0)
