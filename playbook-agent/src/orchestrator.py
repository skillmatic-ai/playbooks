"""Orchestrator — sequential step execution with checkpoint/resume awareness.

For each step (in order), creates a K8s Job for the step agent, then monitors
the step's Firestore status until it reaches "completed" or "failed".

With checkpoint/resume (Issue 15), a step agent may exit its pod cleanly
(Job succeeds) while the step is still "paused" waiting for user input.
The Firebase Function onInputReceived creates a new resume Job when the user
responds.  The orchestrator keeps monitoring Firestore until the step truly
completes — it does NOT advance on K8s Job success alone.

On any step failure the remaining steps are marked as skipped and the run fails.
DAG-aware parallel scheduling is deferred to Issue 16 (dag_scheduler.py).
"""

from __future__ import annotations

import os
import time

from src.firestore_client import (
    initialize_step_docs,
    read_step_status,
    update_run_status,
    update_step_status,
    write_event,
)
from src.k8s_client import create_step_job, resolve_image
from src.playbook_parser import PlaybookDefinition, StepDef

SHARED_ROOT = "/shared"
DEFAULT_POLL_INTERVAL = 10  # seconds


class StepFailedError(Exception):
    """Raised when a step Job fails or times out."""

    def __init__(self, step_id: str, message: str) -> None:
        self.step_id = step_id
        super().__init__(f"Step {step_id} failed: {message}")


# ---------------------------------------------------------------------------
# Report reader
# ---------------------------------------------------------------------------


def _read_step_report(step_id: str) -> str | None:
    """Read a step's completion report from the shared PVC (best-effort)."""
    path = os.path.join(SHARED_ROOT, "results", step_id, "report.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


# ---------------------------------------------------------------------------
# Firestore-based step monitoring
# ---------------------------------------------------------------------------


def _monitor_step_status(
    org_id: str,
    run_id: str,
    step_id: str,
    timeout_seconds: int,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
) -> str:
    """Poll Firestore step status until a terminal state is reached.

    Returns the final status: "completed" or "failed".

    With checkpoint/resume, the lifecycle is:
      pending -> running -> paused -> running -> ... -> completed/failed

    The orchestrator treats "paused" as a transient state (the step agent
    checkpointed and exited, user input is pending, a resume Job will be
    created by onInputReceived).

    Raises StepFailedError on timeout.
    """
    paused_notified = False
    start = time.time()

    while True:
        status = read_step_status(org_id, run_id, step_id)

        if status == "completed":
            return "completed"

        if status == "failed":
            return "failed"

        if status == "skipped":
            return "skipped"

        if status == "paused" and not paused_notified:
            paused_notified = True
            write_event(
                org_id, run_id, "progress",
                step_id=step_id,
                payload={"message": "Waiting for user input (pod terminated, checkpoint saved)"},
            )
            print(f"[orchestrator] Step {step_id} is paused — waiting for user input")

        if status == "running" and paused_notified:
            # Step was resumed — reset the paused flag for future pauses
            paused_notified = False
            write_event(
                org_id, run_id, "progress",
                step_id=step_id,
                payload={"message": "Step resumed after user input"},
            )
            print(f"[orchestrator] Step {step_id} resumed from pause")

        elapsed = time.time() - start
        if elapsed > timeout_seconds:
            raise StepFailedError(
                step_id, f"Step timed out after {timeout_seconds}s"
            )

        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Single step execution
# ---------------------------------------------------------------------------


def _run_step(
    step: StepDef,
    org_id: str,
    run_id: str,
    namespace: str,
    pvc_name: str,
) -> None:
    """Execute a single step: create Job -> monitor Firestore status -> handle result."""
    step_id = step.id

    # Mark running
    update_step_status(org_id, run_id, step_id, "running")
    write_event(
        org_id, run_id, "step_started",
        step_id=step_id,
        payload={"stepId": step_id, "title": step.title},
    )
    print(f"[orchestrator] Step {step_id} ({step.title}) -> running")

    # Resolve image
    image = resolve_image(step.agent_image)
    print(f"[orchestrator] Image: {image}")

    # Create K8s Job
    job_name = create_step_job(
        run_id=run_id,
        step_id=step_id,
        image=image,
        org_id=org_id,
        pvc_name=pvc_name,
        timeout_minutes=step.timeout_minutes,
    )
    update_step_status(org_id, run_id, step_id, "running", job_name=job_name)
    print(f"[orchestrator] Created Job: {job_name}")

    # Monitor step via Firestore status (not K8s Job status).
    # The step agent may checkpoint/exit multiple times (paused -> running cycles)
    # before reaching a terminal state.  The orchestrator waits for "completed"
    # or "failed" in Firestore regardless of K8s Job lifecycle.
    final_status = _monitor_step_status(
        org_id, run_id, step_id,
        timeout_seconds=step.timeout_minutes * 60,
    )

    if final_status == "completed":
        # Read report (best-effort)
        report = _read_step_report(step_id)
        summary = f"Step completed. Report: {len(report)} chars" if report else "Step completed (no report)."

        update_step_status(
            org_id, run_id, step_id, "completed",
            result_summary=summary,
        )
        write_event(
            org_id, run_id, "step_completed",
            step_id=step_id,
            payload={"stepId": step_id, "resultSummary": summary},
        )
        print(f"[orchestrator] Step {step_id} completed: {summary}")
    elif final_status == "skipped":
        print(f"[orchestrator] Step {step_id} was skipped")
    else:
        error_msg = f"Step {step_id} failed (detected via Firestore status)"
        update_step_status(
            org_id, run_id, step_id, "failed",
            error={"code": "STEP_FAILED", "message": error_msg},
        )
        write_event(
            org_id, run_id, "step_failed",
            step_id=step_id,
            payload={"stepId": step_id, "error": error_msg},
        )
        print(f"[orchestrator] Step {step_id} FAILED")
        raise StepFailedError(step_id, error_msg)


# ---------------------------------------------------------------------------
# Main orchestration loop
# ---------------------------------------------------------------------------


def run_orchestration(
    playbook: PlaybookDefinition,
    org_id: str,
    run_id: str,
    namespace: str,
    pvc_name: str,
) -> None:
    """Execute all playbook steps sequentially.

    Raises StepFailedError if any step fails (remaining steps are skipped).
    """
    steps = sorted(playbook.steps, key=lambda s: s.order)

    if not steps:
        print("[orchestrator] No steps to execute")
        return

    # Initialize all step docs as "pending"
    initialize_step_docs(org_id, run_id, steps)
    print(f"[orchestrator] Initialized {len(steps)} step docs")

    completed_count = 0
    total = len(steps)

    for i, step in enumerate(steps):
        step_num = i + 1

        # Progress event: preparing this step
        write_event(
            org_id, run_id, "progress",
            payload={
                "message": f"Preparing step {step_num} of {total}: {step.title}",
            },
        )
        print(f"[orchestrator] Preparing step {step_num}/{total}: {step.title}")

        # Update currentStepId on the run doc
        update_run_status(org_id, run_id, "running", current_step_id=step.id)

        try:
            _run_step(step, org_id, run_id, namespace, pvc_name)
            completed_count += 1

            # Context-passing event if there's a next step
            if i + 1 < total:
                next_step = steps[i + 1]
                write_event(
                    org_id, run_id, "progress",
                    payload={
                        "message": (
                            f"Step {step_num} complete — forwarding results "
                            f"to step {step_num + 1}: {next_step.title}"
                        ),
                    },
                )
                print(
                    f"[orchestrator] Forwarding results -> "
                    f"step {step_num + 1}: {next_step.title}"
                )
        except StepFailedError:
            # Mark remaining steps as skipped
            for remaining in steps[i + 1:]:
                update_step_status(org_id, run_id, remaining.id, "skipped")
                print(f"[orchestrator] Step {remaining.id} -> skipped")
            raise

    print(f"[orchestrator] All {completed_count}/{total} steps completed")
