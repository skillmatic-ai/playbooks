"""Interactive Step Agent — demonstrates HITL checkpoint/resume flow.

Lifecycle:
  Phase 1 (fresh):  startup -> ask question -> checkpoint -> pod exits
  Phase 2 (resume): read answer -> build draft -> request approval -> checkpoint -> pod exits
  Phase 3 (resume): read decision -> write report -> complete

Each HITL interaction (question, approval) causes the pod to terminate.
The Firebase Function onInputReceived creates a new K8s Job on user response,
passing RESUME_THREAD_ID so the entrypoint knows to load the checkpoint.
"""

import os
import sys
import traceback

from step_agent.checkpoint import clear_checkpoint, load_checkpoint
from step_agent.firestore_client import (
    read_input,
    read_run_context,
    read_run_status,
    update_step_status,
    write_event,
)
from step_agent.hitl_tools import (
    RunAbortedError,
    ask_user,
    request_approval,
)
from step_agent.skill_loader import load_skill
from step_agent.file_tools import write_report


# ---------------------------------------------------------------------------
# Phase functions
# ---------------------------------------------------------------------------


def _phase_fresh(org_id: str, run_id: str, step_id: str) -> None:
    """Phase 1: fresh start — load skill, read context, ask question."""
    update_step_status(org_id, run_id, step_id, "running")
    write_event(
        org_id, run_id, "step_started",
        step_id=step_id,
        payload={"stepId": step_id},
    )

    # Load SKILL.md
    skill = load_skill("/app/skills")
    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": f"Loaded skill: {skill.name}"},
    )

    # Read context
    write_event(
        org_id, run_id, "agent_thinking",
        step_id=step_id,
        payload={"thought": "Reading run context and preparing question..."},
    )
    context = read_run_context(org_id, run_id)

    # Ask user — this checkpoints and exits (never returns)
    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": "Asking user for input", "percent": 20},
    )
    ask_user(
        org_id, run_id, step_id,
        question="What is the main objective for this project? Please describe briefly.",
        question_type="free_text",
        help_text="This will be used to generate a project summary draft.",
        checkpoint_data={"context": context},
    )
    # Pod exits inside ask_user — execution never reaches here


def _phase_after_question(
    org_id: str,
    run_id: str,
    step_id: str,
    user_answer: str,
    checkpoint_data: dict,
) -> None:
    """Phase 2: user answered the question — build draft, request approval."""
    update_step_status(org_id, run_id, step_id, "running")
    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": "Resumed — processing user answer", "percent": 40},
    )

    print(f"[step-agent] User answered: {user_answer}")
    write_event(
        org_id, run_id, "agent_tool_use",
        step_id=step_id,
        payload={
            "toolName": "ask_user",
            "args": {"questionType": "free_text"},
            "result": f"Received answer: {len(user_answer)} chars",
        },
    )

    # Build draft from user input
    write_event(
        org_id, run_id, "agent_thinking",
        step_id=step_id,
        payload={"thought": "Building project summary draft from user input..."},
    )
    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": "Generating draft document", "percent": 50},
    )

    context = checkpoint_data.get("context", {})
    draft = (
        f"# Project Summary\n\n"
        f"## Objective\n\n{user_answer}\n\n"
        f"## Context\n\n"
    )
    if context:
        for key, value in sorted(context.items()):
            draft += f"- **{key}**: {value}\n"
    else:
        draft += "_No additional context available._\n"
    draft += (
        f"\n## Metadata\n\n"
        f"- Run: `{run_id}`\n"
        f"- Step: `{step_id}`\n"
        f"- Org: `{org_id}`\n"
    )

    # Request approval — this checkpoints and exits (never returns)
    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": "Requesting approval on draft", "percent": 70},
    )
    request_approval(
        org_id, run_id, step_id,
        description="Please review the generated project summary draft.",
        draft_content=draft,
        risk_level="low",
        checkpoint_data={"draft": draft, "user_answer": user_answer},
    )
    # Pod exits inside request_approval — execution never reaches here


def _phase_after_approval(
    org_id: str,
    run_id: str,
    step_id: str,
    decision: dict,
    checkpoint_data: dict,
) -> None:
    """Phase 3: user approved/rejected — write report, complete."""
    update_step_status(org_id, run_id, step_id, "running")
    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": "Resumed — processing approval decision", "percent": 80},
    )

    decision_value = decision.get("decision", "reject")
    print(f"[step-agent] Approval decision: {decision_value}")

    write_event(
        org_id, run_id, "agent_tool_use",
        step_id=step_id,
        payload={
            "toolName": "request_approval",
            "args": {"riskLevel": "low"},
            "result": f"Decision: {decision_value}",
        },
    )

    # Build final report based on decision
    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": "Writing final report", "percent": 90},
    )

    draft = checkpoint_data.get("draft", "")

    if decision_value == "approve":
        report_content = draft + "\n---\n\n_Approved by user._\n"
        summary = "Draft approved and finalized."
    elif decision_value == "revise":
        revised = decision.get("revisedContent") or draft
        report_content = revised + "\n---\n\n_Revised by user._\n"
        summary = "Draft revised by user and finalized."
    else:
        report_content = draft + "\n---\n\n_Rejected by user._\n"
        summary = "Draft rejected by user."

    report_path = write_report(step_id, report_content)
    print(f"[step-agent] Wrote report to {report_path}")

    # Clean up checkpoint
    clear_checkpoint(org_id, run_id, step_id)

    # Mark step as completed
    write_event(
        org_id, run_id, "step_completed",
        step_id=step_id,
        payload={"resultSummary": summary},
    )
    update_step_status(
        org_id, run_id, step_id, "completed",
        result_summary=summary,
    )
    print(f"[step-agent] Step completed: {summary}")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    run_id = os.environ.get("RUN_ID")
    org_id = os.environ.get("ORG_ID")
    step_id = os.environ.get("STEP_ID", "unknown")
    resume_thread_id = os.environ.get("RESUME_THREAD_ID")

    if not run_id or not org_id:
        print("[step-agent] ERROR: RUN_ID and ORG_ID env vars are required")
        sys.exit(1)

    print(f"[step-agent] Starting interactive step={step_id} run={run_id} org={org_id}")
    if resume_thread_id:
        print(f"[step-agent] Resuming from checkpoint (thread={resume_thread_id})")

    try:
        if not resume_thread_id:
            # Fresh start
            _phase_fresh(org_id, run_id, step_id)
        else:
            # Resume from checkpoint (stored in Firestore on the step doc)
            checkpoint = load_checkpoint(org_id, run_id, step_id)
            if checkpoint is None:
                raise RuntimeError(
                    f"RESUME_THREAD_ID set but no checkpoint found for step {step_id}"
                )

            # Check if run was aborted while paused
            run_status = read_run_status(org_id, run_id)
            if run_status == "aborted":
                raise RunAbortedError("Run was aborted while step was paused")

            # Read the input that triggered this resume
            question_id = checkpoint["questionId"]
            input_doc = read_input(org_id, run_id, question_id)
            if input_doc is None:
                raise RuntimeError(
                    f"Resume triggered but input not found for questionId={question_id}"
                )

            if input_doc.get("type") == "abort":
                raise RunAbortedError("Run was aborted via input")

            phase = checkpoint.get("phase", "")
            data = checkpoint.get("data", {})

            if phase == "waiting_for_answer":
                user_answer = input_doc.get("payload", {}).get("answer", "")
                _phase_after_question(org_id, run_id, step_id, user_answer, data)
            elif phase == "waiting_for_approval":
                decision = {
                    "decision": input_doc.get("payload", {}).get("decision", "reject"),
                    "revisedContent": input_doc.get("payload", {}).get("revisedContent"),
                }
                _phase_after_approval(org_id, run_id, step_id, decision, data)
            else:
                raise RuntimeError(f"Unknown checkpoint phase: {phase}")

    except SystemExit:
        # Let sys.exit() from hitl_tools propagate cleanly
        raise

    except RunAbortedError:
        print("[step-agent] Run was aborted")
        update_step_status(org_id, run_id, step_id, "skipped")
        clear_checkpoint(org_id, run_id, step_id)
        sys.exit(0)

    except Exception as exc:
        print(f"[step-agent] FATAL: {exc}")
        traceback.print_exc()

        try:
            write_event(
                org_id, run_id, "step_failed",
                step_id=step_id,
                payload={"error": str(exc)},
            )
            update_step_status(
                org_id, run_id, step_id, "failed",
                error={"code": "STEP_AGENT_CRASH", "message": str(exc)},
            )
        except Exception:
            print("[step-agent] Failed to write error status to Firestore")
            traceback.print_exc()

        clear_checkpoint(org_id, run_id, step_id)
        sys.exit(1)


if __name__ == "__main__":
    main()
