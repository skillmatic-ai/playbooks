"""Orchestrator — DAG-aware parallel step scheduling with checkpoint/resume.

Evaluates each step's ``dependencies`` field and runs independent steps
concurrently.  Steps with no unsatisfied dependencies start simultaneously;
dependent steps wait until all their dependencies complete.

With checkpoint/resume (Issue 15), a step agent may exit its pod cleanly
(Job succeeds) while the step is still "paused" waiting for user input.
The Firebase Function onInputReceived creates a new resume Job when the user
responds.  The orchestrator keeps monitoring Firestore until the step truly
completes — it does NOT advance on K8s Job success alone.

Failure handling: when a step fails, its transitive dependents are skipped
immediately.  Parallel siblings (steps with no dependency on the failed step)
continue to completion.  The run is marked as failed once all possible steps
finish.

Playbooks that need sequential execution should declare explicit ``dependencies``
chains.  Steps with no dependencies launch immediately in parallel.
"""

from __future__ import annotations

import os
import time
import uuid

from src.dag_scheduler import (
    get_ready_steps,
    get_transitive_dependents,
    validate_dag,
)
from src.firestore_client import (
    check_token_exists,
    fetch_role_members,
    initialize_step_docs,
    read_role_assignments,
    read_run,
    read_step_input_response,
    read_step_input_values,
    read_step_report,
    read_step_status,
    update_run_heartbeat,
    update_run_status,
    update_step_status,
    write_event,
    write_prior_reports,
    write_step_input_request_id,
    write_step_input_values,
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


class RunAbortedError(Exception):
    """Raised when the run is aborted by a user during orchestration."""


# ---------------------------------------------------------------------------
# Report reader
# ---------------------------------------------------------------------------


def _read_step_report_local(step_id: str) -> str | None:
    """Read a step's completion report from the shared volume (best-effort)."""
    path = os.path.join(SHARED_ROOT, "results", step_id, "report.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def _collect_prior_reports(
    step: StepDef,
    step_map: dict[str, StepDef],
    org_id: str,
    run_id: str,
) -> str:
    """Collect reports from all dependency steps and format as context string.

    Returns a formatted string of all prior reports, or empty string if none.
    """
    if not step.dependencies:
        return ""

    sections: list[str] = []
    for dep_id in step.dependencies:
        dep = step_map.get(dep_id)
        dep_title = dep.title if dep else dep_id
        report = read_step_report(org_id, run_id, dep_id) or _read_step_report_local(dep_id)
        if report:
            sections.append(
                f'=== Report from "{dep_title}" (completed) ===\n{report}'
            )

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# OAuth token check (Issue 24)
# ---------------------------------------------------------------------------


def _check_oauth_and_launch(
    step: StepDef,
    org_id: str,
    run_id: str,
    namespace: str,
    oauth_notified: set[str],
    input_notified: set[str],
    step_map: dict[str, StepDef],
    role_assignments: dict[str, dict] | None = None,
) -> str:
    """Check OAuth token and step inputs before launching.

    Returns:
        'launched'       — step was launched successfully
        'waiting_oauth'  — waiting for user to connect OAuth
        'waiting_input'  — OAuth ok, but waiting for JIT step inputs
    """
    # Collect prior reports for dependency injection
    prior_reports = _collect_prior_reports(step, step_map, org_id, run_id)

    if not step.api:
        # No API required — check step inputs then launch
        if not _check_step_inputs(step, org_id, run_id, input_notified):
            return "waiting_input"
        _launch_step(step, org_id, run_id, namespace, prior_reports=prior_reports)
        return "launched"

    # Resolve role → user (primary: roleAssignments, fallback: Firestore query)
    role = step.assigned_role
    assignment = (role_assignments or {}).get(role) if role else None

    if assignment:
        target_uid = assignment.get("memberId", "")
        target_name = assignment.get("name", assignment.get("email", "User"))
    else:
        members = fetch_role_members(org_id, role) if role else []
        if not members:
            print(f"[orchestrator] No member with role '{role}' — launching anyway")
            if not _check_step_inputs(step, org_id, run_id, input_notified):
                return "waiting_input"
            _launch_step(step, org_id, run_id, namespace, prior_reports=prior_reports)
            return "launched"
        target_uid = members[0].get("uid", "")
        target_name = members[0].get("displayName", members[0].get("email", "User"))

    if not target_uid:
        print(f"[orchestrator] Member has no uid — launching anyway")
        if not _check_step_inputs(step, org_id, run_id, input_notified):
            return "waiting_input"
        _launch_step(step, org_id, run_id, namespace, prior_reports=prior_reports)
        return "launched"

    # Check if token exists
    has_token = check_token_exists(org_id, target_uid, step.api)

    if has_token:
        print(f"[orchestrator] OAuth token found for {target_name} / {step.api}")
        # OAuth ok — now check step inputs before launching
        if not _check_step_inputs(step, org_id, run_id, input_notified):
            return "waiting_input"
        _launch_step(step, org_id, run_id, namespace, prior_reports=prior_reports)
        return "launched"

    # Token missing — emit event and pause
    if step.id not in oauth_notified:
        oauth_notified.add(step.id)
        write_event(
            org_id, run_id, "oauth_required",
            step_id=step.id,
            payload={
                "service": step.api,
                "targetUserId": target_uid,
                "targetUserName": target_name,
                "targetRole": role,
                "scopes": step.required_connections,
                "message": f"{target_name} needs to connect {step.api.title()}",
            },
        )
        update_step_status(org_id, run_id, step.id, "waiting_for_oauth")
        print(f"[orchestrator] Step {step.id} -> waiting_for_oauth ({target_name} / {step.api})")

    return "waiting_oauth"


# ---------------------------------------------------------------------------
# JIT step input check
# ---------------------------------------------------------------------------


def _check_step_inputs(
    step: StepDef,
    org_id: str,
    run_id: str,
    input_notified: set[str],
) -> bool:
    """Check if a step requires JIT inputs before launching.

    Returns True if no inputs needed or inputs already provided.
    Returns False if the step is waiting for user input.
    """
    if not step.inputs:
        return True  # No step-level inputs declared

    # Check if response already exists (idempotent re-check)
    existing = read_step_input_response(org_id, run_id, step.id)
    if existing:
        return True

    if step.id not in input_notified:
        input_notified.add(step.id)
        request_id = str(uuid.uuid4())
        write_event(
            org_id, run_id, "step_input_request",
            step_id=step.id,
            payload={
                "stepInputRequestId": request_id,
                "targetRole": step.assigned_role,
                "stepTitle": step.title,
                "service": step.api,
                "inputs": [
                    {
                        "name": inp.name,
                        "type": inp.type,
                        "label": inp.label or inp.name,
                        "placeholder": inp.placeholder,
                        "required": inp.required,
                    }
                    for inp in step.inputs
                ],
            },
        )
        update_step_status(org_id, run_id, step.id, "waiting_for_input")
        write_step_input_request_id(org_id, run_id, step.id, request_id)
        print(f"[orchestrator] Step {step.id} -> waiting_for_input ({len(step.inputs)} input(s) requested)")

    return False


# ---------------------------------------------------------------------------
# Step launch (non-blocking)
# ---------------------------------------------------------------------------


def _launch_step(
    step: StepDef,
    org_id: str,
    run_id: str,
    namespace: str,
    *,
    prior_reports: str = "",
) -> str:
    """Launch a step's K8s Job without blocking for completion.

    Updates Firestore status to 'running', writes a step_started event,
    resolves the container image, and creates the K8s Job.

    If prior_reports is provided, writes it to the step doc so the agent
    can read it via context_reader.
    Returns the job_name.
    """
    step_id = step.id

    update_step_status(org_id, run_id, step_id, "running")

    # Write prior reports to step doc for the agent to consume
    if prior_reports:
        write_prior_reports(org_id, run_id, step_id, prior_reports)
        print(f"[orchestrator] Injected {len(prior_reports)} chars of prior reports for {step_id}")

    write_event(
        org_id, run_id, "step_started",
        step_id=step_id,
        payload={"stepId": step_id, "title": step.title},
    )
    print(f"[orchestrator] Step {step_id} ({step.title}) -> running")

    image = resolve_image(step.agent_image)
    print(f"[orchestrator] Image: {image}")

    job_name = create_step_job(
        run_id=run_id,
        step_id=step_id,
        image=image,
        org_id=org_id,
        timeout_minutes=step.timeout_minutes,
    )
    update_step_status(org_id, run_id, step_id, "running", job_name=job_name)
    print(f"[orchestrator] Created Job: {job_name}")
    return job_name


# ---------------------------------------------------------------------------
# Single-poll status check
# ---------------------------------------------------------------------------


def _poll_step_once(
    org_id: str,
    run_id: str,
    step_id: str,
    paused_notified: dict[str, bool],
) -> str | None:
    """Check a single step's Firestore status once.

    Returns the status string if terminal ("completed", "failed", "skipped"),
    or None if the step is still in-progress (running/paused/pending).

    Handles paused/resumed notification side-effects.
    The ``paused_notified`` dict is mutated in-place for tracking.
    """
    status = read_step_status(org_id, run_id, step_id)

    if status in ("completed", "failed", "skipped"):
        return status

    if status == "paused" and not paused_notified.get(step_id, False):
        paused_notified[step_id] = True
        write_event(
            org_id, run_id, "progress",
            step_id=step_id,
            payload={"message": "Waiting for user input (pod terminated, checkpoint saved)"},
        )
        print(f"[orchestrator] Step {step_id} is paused — waiting for user input")

    if status == "running" and paused_notified.get(step_id, False):
        paused_notified[step_id] = False
        write_event(
            org_id, run_id, "progress",
            step_id=step_id,
            payload={"message": "Step resumed after user input"},
        )
        print(f"[orchestrator] Step {step_id} resumed from pause")

    # waiting_for_oauth → ready transition: token was granted, re-launch needed
    if status == "ready":
        return "ready"

    return None  # still in progress


# ---------------------------------------------------------------------------
# Step completion handler
# ---------------------------------------------------------------------------


def _handle_step_completion(
    step: StepDef,
    final_status: str,
    org_id: str,
    run_id: str,
) -> None:
    """Process a step that reached a terminal Firestore status."""
    step_id = step.id

    if final_status == "completed":
        # Read report: prefer Firestore (written by API agent), fall back to local
        report = read_step_report(org_id, run_id, step_id) or _read_step_report_local(step_id)
        summary = (
            f"Step completed. Report: {len(report)} chars"
            if report
            else "Step completed (no report)."
        )
        has_report = report is not None and len(report) > 0
        update_step_status(
            org_id, run_id, step_id, "completed",
            result_summary=summary,
        )
        write_event(
            org_id, run_id, "step_completed",
            step_id=step_id,
            payload={
                "stepId": step_id,
                "resultSummary": summary,
                "hasReport": has_report,
            },
        )
        print(f"[orchestrator] Step {step_id} completed: {summary}")

    elif final_status == "failed":
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

    elif final_status == "skipped":
        print(f"[orchestrator] Step {step_id} was skipped")


# ---------------------------------------------------------------------------
# Failure cascade — skip transitive dependents
# ---------------------------------------------------------------------------


def _skip_transitive_dependents(
    failed_step_id: str,
    steps: list[StepDef],
    org_id: str,
    run_id: str,
    already_skipped: set[str],
    completed: set[str],
    running: set[str],
) -> set[str]:
    """Mark all transitive dependents of a failed step as skipped.

    Only skips steps that are not already completed, running, or skipped.
    Returns the set of newly skipped step IDs.
    """
    to_skip = get_transitive_dependents(failed_step_id, steps)
    to_skip -= completed | running | already_skipped

    newly_skipped: set[str] = set()
    for skip_id in to_skip:
        update_step_status(org_id, run_id, skip_id, "skipped")
        write_event(
            org_id, run_id, "progress",
            step_id=skip_id,
            payload={"message": f"Step skipped (dependency '{failed_step_id}' failed)"},
        )
        print(f"[orchestrator] Step {skip_id} -> skipped (depends on failed {failed_step_id})")
        newly_skipped.add(skip_id)

    return newly_skipped


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------


def _write_summary(
    steps: list[StepDef],
    completed: set[str],
    failed: set[str],
    skipped: set[str],
) -> None:
    """Log summary and raise StepFailedError if any steps failed."""
    total = len(steps)
    c, f, s = len(completed), len(failed), len(skipped)

    if f == 0 and s == 0:
        print(f"[orchestrator] All {c}/{total} steps completed")
        return

    summary = f"{c} of {total} steps completed, {f} failed, {s} skipped"
    print(f"[orchestrator] {summary}")

    failed_ids = sorted(failed)
    raise StepFailedError(
        failed_ids[0],
        f"Run failed: {summary}. Failed steps: {failed_ids}",
    )


# ---------------------------------------------------------------------------
# Main orchestration loop
# ---------------------------------------------------------------------------


def run_orchestration(
    playbook: PlaybookDefinition,
    org_id: str,
    run_id: str,
    namespace: str,
) -> None:
    """Execute playbook steps using DAG-aware parallel scheduling.

    Steps with satisfied dependencies launch concurrently.
    On failure: parallel siblings continue to completion, but transitive
    dependents of the failed step are skipped.

    Raises StepFailedError if any step fails (after all possible steps finish).
    """
    steps = sorted(playbook.steps, key=lambda s: s.order)

    if not steps:
        print("[orchestrator] No steps to execute")
        return

    # --- Validate DAG ---
    validate_dag(steps)
    print(f"[orchestrator] DAG validated: {len(steps)} steps, no cycles")

    # --- Initialize Firestore step docs ---
    initialize_step_docs(org_id, run_id, steps)
    print(f"[orchestrator] Initialized {len(steps)} step docs")

    # --- Load role assignments from run doc ---
    role_assignments = read_role_assignments(org_id, run_id)
    if role_assignments:
        print(f"[orchestrator] Role assignments: {list(role_assignments.keys())}")
    else:
        print("[orchestrator] No role assignments on run doc — will use Firestore member lookup")

    # --- Build step lookup ---
    step_map: dict[str, StepDef] = {s.id: s for s in steps}
    total = len(steps)

    # --- State tracking ---
    completed: set[str] = set()
    failed: set[str] = set()
    running: set[str] = set()
    skipped: set[str] = set()
    waiting_oauth: set[str] = set()  # Steps waiting for OAuth token grant
    waiting_input: set[str] = set()  # Steps waiting for JIT step inputs
    oauth_notified: set[str] = set()  # Steps that already emitted oauth_required
    input_notified: set[str] = set()  # Steps that already emitted step_input_request
    paused_notified: dict[str, bool] = {}
    step_start_times: dict[str, float] = {}

    # --- Main DAG scheduling loop ---
    while True:
        # 1. Launch newly ready steps (exclude those waiting for OAuth or input)
        ready = get_ready_steps(
            steps, completed, failed | skipped, running | waiting_oauth | waiting_input,
        )

        if ready:
            if len(ready) > 1:
                ids = [s.id for s in ready]
                write_event(
                    org_id, run_id, "progress",
                    payload={"message": f"Starting steps in parallel: [{', '.join(ids)}]"},
                )
                print(f"[orchestrator] Launching parallel: {ids}")

            for step in ready:
                write_event(
                    org_id, run_id, "progress",
                    payload={
                        "message": f"Preparing step {step.order} of {total}: {step.title}",
                    },
                )
                update_run_status(org_id, run_id, "running", current_step_id=step.id)

                result = _check_oauth_and_launch(
                    step, org_id, run_id, namespace, oauth_notified, input_notified, step_map,
                    role_assignments=role_assignments,
                )
                if result == "launched":
                    running.add(step.id)
                    step_start_times[step.id] = time.time()
                elif result == "waiting_oauth":
                    waiting_oauth.add(step.id)
                elif result == "waiting_input":
                    waiting_input.add(step.id)

        # 1b. Re-check waiting_for_oauth steps (token may have been granted)
        for step_id in list(waiting_oauth):
            status = read_step_status(org_id, run_id, step_id)
            if status == "ready":
                # Token was granted — onOAuthGranted set status to "ready"
                step = step_map[step_id]
                waiting_oauth.discard(step_id)

                # After OAuth clears, check if step needs JIT inputs
                inputs_ok = _check_step_inputs(step, org_id, run_id, input_notified)
                if not inputs_ok:
                    waiting_input.add(step_id)
                    print(f"[orchestrator] Step {step_id} OAuth granted — now waiting for inputs")
                    continue

                prior = _collect_prior_reports(step, step_map, org_id, run_id)
                print(f"[orchestrator] Step {step_id} OAuth granted — launching")
                _launch_step(step, org_id, run_id, namespace, prior_reports=prior)
                running.add(step_id)
                step_start_times[step_id] = time.time()

        # 1c. Re-check waiting_for_input steps (user may have provided input)
        for step_id in list(waiting_input):
            response = read_step_input_response(org_id, run_id, step_id)
            if response:
                step = step_map[step_id]
                waiting_input.discard(step_id)
                # Write resolved values to step doc
                values = (response.get("payload") or {}).get("values", {})
                write_step_input_values(org_id, run_id, step_id, values)
                prior = _collect_prior_reports(step, step_map, org_id, run_id)
                print(f"[orchestrator] Step {step_id} inputs received — launching")
                _launch_step(step, org_id, run_id, namespace, prior_reports=prior)
                running.add(step_id)
                step_start_times[step_id] = time.time()

        # 2. Check termination: nothing running/waiting and nothing more can be launched
        if not running and not waiting_oauth and not waiting_input:
            remaining = {s.id for s in steps} - completed - failed - skipped
            if not remaining:
                break

            # Remaining steps are blocked by failures — mark them skipped
            for rem_id in remaining:
                update_step_status(org_id, run_id, rem_id, "skipped")
                write_event(
                    org_id, run_id, "progress",
                    step_id=rem_id,
                    payload={"message": "Step skipped (blocked by failed dependency)"},
                )
                print(f"[orchestrator] Step {rem_id} -> skipped (blocked)")
                skipped.add(rem_id)
            break

        # 3. Poll all running steps once
        for step_id in list(running):
            step = step_map[step_id]

            # Timeout check
            elapsed = time.time() - step_start_times.get(step_id, time.time())
            timeout_seconds = step.timeout_minutes * 60

            if elapsed > timeout_seconds:
                error_msg = f"Step timed out after {timeout_seconds}s"
                update_step_status(
                    org_id, run_id, step_id, "failed",
                    error={"code": "STEP_TIMEOUT", "message": error_msg},
                )
                write_event(
                    org_id, run_id, "step_failed",
                    step_id=step_id,
                    payload={"stepId": step_id, "error": error_msg},
                )
                print(f"[orchestrator] Step {step_id} TIMED OUT")
                running.discard(step_id)
                failed.add(step_id)
                newly_skipped = _skip_transitive_dependents(
                    step_id, steps, org_id, run_id, skipped, completed, running,
                )
                skipped |= newly_skipped
                continue

            # Normal status poll
            result = _poll_step_once(org_id, run_id, step_id, paused_notified)

            if result is not None:
                if result == "ready":
                    # Step was re-set to ready (e.g. OAuth granted) — re-launch
                    running.discard(step_id)
                    prior = _collect_prior_reports(step, step_map, org_id, run_id)
                    _launch_step(step, org_id, run_id, namespace, prior_reports=prior)
                    running.add(step_id)
                    step_start_times[step_id] = time.time()
                    continue

                running.discard(step_id)
                _handle_step_completion(step, result, org_id, run_id)

                if result == "completed":
                    completed.add(step_id)

                elif result == "failed":
                    failed.add(step_id)
                    newly_skipped = _skip_transitive_dependents(
                        step_id, steps, org_id, run_id, skipped, completed, running,
                    )
                    skipped |= newly_skipped

                elif result == "skipped":
                    skipped.add(step_id)

        # 4. Check for abort
        run_data = read_run(org_id, run_id)
        if run_data and run_data.get("status") == "aborted":
            print("[orchestrator] Run aborted by user — exiting gracefully")
            for sid in list(running):
                update_step_status(org_id, run_id, sid, "skipped")
                skipped.add(sid)
            running.clear()
            raise RunAbortedError("Run aborted by user")

        # 5. Sleep + heartbeat
        time.sleep(DEFAULT_POLL_INTERVAL)
        update_run_heartbeat(org_id, run_id)

    # --- Final summary ---
    _write_summary(steps, completed, failed, skipped)
