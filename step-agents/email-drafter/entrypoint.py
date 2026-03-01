"""Email Drafter Step Agent — 3-phase HITL checkpoint/resume.

Phase 1 (fresh):  Load skill -> read context -> LLM generates contextual question -> checkpoint -> pod exits
Phase 2 (resume): Read answer -> LLM drafts personalized welcome email -> request review_and_edit -> checkpoint -> pod exits
Phase 3 (resume): Read decision -> send via Gmail API -> write report -> complete

Uses Claude API for content generation and Gmail API for actual email delivery.
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
from step_agent.gmail_client import send_email
from step_agent.hitl_tools import (
    RunAbortedError,
    ask_user,
    request_approval,
)
from step_agent.llm_client import generate
from step_agent.skill_loader import load_skill
from step_agent.storage_tools import write_report


# ---------------------------------------------------------------------------
# Phase functions
# ---------------------------------------------------------------------------


def _phase_fresh(org_id: str, run_id: str, step_id: str) -> None:
    """Phase 1: fresh start — load skill, read context, LLM generates question."""
    update_step_status(org_id, run_id, step_id, "running")
    write_event(
        org_id, run_id, "step_started",
        step_id=step_id,
        payload={"stepId": step_id},
    )

    skill = load_skill("/app/skills")
    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": f"Loaded skill: {skill.name}"},
    )

    context = read_run_context(org_id, run_id)
    new_hire = context.get("new_hire_name", "the new hire")
    company = context.get("company_name", "the company")

    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={
            "message": f"Preparing welcome email for {new_hire}",
            "percent": 10,
        },
    )

    # LLM generates a contextual question about what to include
    question = generate(
        org_id, run_id, step_id,
        system_prompt=(
            "You are an HR onboarding specialist. Generate a single, clear question "
            "to ask the hiring manager about any special topics or information to "
            "include in the welcome email. Keep it concise (1-2 sentences)."
        ),
        user_prompt=(
            f"We're drafting a welcome email for {new_hire} joining {company} "
            f"as a new employee. What question should we ask the hiring manager "
            f"about special topics to include? Examples: team events, parking info, "
            f"remote work policy, specific projects they'll join."
        ),
        max_tokens=200,
        temperature=0.7,
    )

    # Ask user — this checkpoints and exits (never returns)
    ask_user(
        org_id, run_id, step_id,
        question=question.strip(),
        question_type="free_text",
        help_text="Type 'none' or leave blank if there are no special topics.",
        required=False,
        checkpoint_data={"context": context},
    )
    # Pod exits here — never returns


def _phase_after_question(
    org_id: str,
    run_id: str,
    step_id: str,
    user_answer: str,
    checkpoint_data: dict,
) -> None:
    """Phase 2: user answered the question — LLM drafts email, request approval."""
    update_step_status(org_id, run_id, step_id, "running")
    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": "Resumed — generating welcome email draft with AI", "percent": 40},
    )

    context = checkpoint_data.get("context", {})
    name = context.get("new_hire_name", "New Team Member")
    company = context.get("company_name", "Our Company")
    email = context.get("new_hire_email", "")
    manager = context.get("manager_email", "your manager")
    start = context.get("start_date", "your start date")

    print(f"[email-drafter] User answer: {user_answer}")

    special_topics_note = ""
    if user_answer and user_answer.strip().lower() != "none":
        special_topics_note = f"\n\nThe hiring manager also wants to include these topics: {user_answer.strip()}"

    # LLM drafts the welcome email
    draft = generate(
        org_id, run_id, step_id,
        system_prompt=(
            "You are a professional HR communications writer. Draft a warm, "
            "personalized welcome email for a new hire. The email should be "
            "professional yet friendly, include a clear week-1 overview, and "
            "make the new hire feel excited about joining. Format as a complete "
            "email with Subject:, To:, CC:, and body. Use markdown formatting."
        ),
        user_prompt=(
            f"Draft a welcome email with these details:\n"
            f"- New hire: {name}\n"
            f"- Email: {email}\n"
            f"- Company: {company}\n"
            f"- Manager: {manager}\n"
            f"- Start date: {start}"
            f"{special_topics_note}\n\n"
            f"Include a 5-day week-1 overview, pre-first-day checklist, "
            f"and a warm closing."
        ),
        max_tokens=2048,
        temperature=0.7,
    )

    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": "Email draft ready — requesting review", "percent": 60},
    )

    # Request approval — this checkpoints and exits (never returns)
    request_approval(
        org_id, run_id, step_id,
        description="Please review the AI-generated welcome email draft. You may approve it as-is, edit it, or reject it.",
        draft_content=draft,
        risk_level="low",
        checkpoint_data={"draft": draft, "user_answer": user_answer, "context": context},
    )
    # Pod exits here — never returns


def _phase_after_approval(
    org_id: str,
    run_id: str,
    step_id: str,
    decision: dict,
    checkpoint_data: dict,
) -> None:
    """Phase 3: user approved/rejected — send via Gmail, write report, complete."""
    update_step_status(org_id, run_id, step_id, "running")
    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": "Resumed — processing approval decision", "percent": 80},
    )

    decision_value = decision.get("decision", "reject")
    draft = checkpoint_data.get("draft", "")
    context = checkpoint_data.get("context", {})
    print(f"[email-drafter] Approval decision: {decision_value}")

    write_event(
        org_id, run_id, "agent_tool_use",
        step_id=step_id,
        payload={
            "toolName": "request_approval",
            "args": {"riskLevel": "low"},
            "result": f"Decision: {decision_value}",
        },
    )

    if decision_value == "approve":
        final_content = draft
    elif decision_value == "revise":
        final_content = decision.get("revisedContent") or draft
    else:
        # Rejected — skip sending, just save the draft
        report_content = draft + "\n---\n\n_Rejected by reviewer. Email was not sent._\n"
        summary = "Welcome email rejected. No email was sent."

        result = write_report(
            org_id, run_id, step_id, report_content,
            title="welcome-email.md",
            description="Welcome email draft (rejected)",
        )
        print(f"[email-drafter] Wrote report: {result['storagePath']}")

        clear_checkpoint(org_id, run_id, step_id)
        write_event(
            org_id, run_id, "step_completed",
            step_id=step_id,
            payload={"resultSummary": summary},
        )
        update_step_status(org_id, run_id, step_id, "completed", result_summary=summary)
        print(f"[email-drafter] Step completed: {summary}")
        sys.exit(0)

    # Approved or revised — send via Gmail API
    recipient = context.get("new_hire_email", "")
    manager_email = context.get("manager_email", "")
    name = context.get("new_hire_name", "New Hire")
    company = context.get("company_name", "Company")

    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": f"Sending welcome email to {recipient} via Gmail", "percent": 85},
    )

    gmail_result = {}
    gmail_status = "skipped"
    try:
        gmail_result = send_email(
            org_id,
            to=recipient,
            subject=f"Welcome to {company}, {name}!",
            body=final_content,
            cc=[manager_email] if manager_email else None,
        )
        gmail_status = f"sent (id={gmail_result.get('id', 'unknown')})"
        print(f"[email-drafter] Gmail sent: {gmail_result}")
        write_event(
            org_id, run_id, "agent_tool_use",
            step_id=step_id,
            payload={
                "toolName": "gmail_send",
                "args": {"to": recipient},
                "result": f"Sent (id={gmail_result.get('id', 'unknown')})",
            },
        )
    except Exception as e:
        gmail_status = f"failed: {e}"
        print(f"[email-drafter] Gmail failed (non-fatal): {e}")

    status_label = "Revised" if decision_value == "revise" else "Approved"
    report_content = final_content + f"\n\n---\n\n_Gmail: {gmail_status}. {status_label} by reviewer._\n"

    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": "Writing final email report", "percent": 90},
    )

    result = write_report(
        org_id, run_id, step_id, report_content,
        title="welcome-email.md",
        description="Welcome email for new hire onboarding",
    )
    print(f"[email-drafter] Wrote report: {result['storagePath']}")

    clear_checkpoint(org_id, run_id, step_id)

    summary = f"Welcome email draft complete. Gmail: {gmail_status}."

    write_event(
        org_id, run_id, "step_completed",
        step_id=step_id,
        payload={"resultSummary": summary},
    )
    update_step_status(
        org_id, run_id, step_id, "completed",
        result_summary=summary,
    )
    print(f"[email-drafter] Step completed: {summary}")
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
        print("[email-drafter] ERROR: RUN_ID and ORG_ID env vars are required")
        sys.exit(1)

    print(f"[email-drafter] Starting step={step_id} run={run_id} org={org_id}")
    if resume_thread_id:
        print(f"[email-drafter] Resuming from checkpoint (thread={resume_thread_id})")

    try:
        if not resume_thread_id:
            _phase_fresh(org_id, run_id, step_id)
        else:
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
        raise

    except RunAbortedError:
        print("[email-drafter] Run was aborted")
        update_step_status(org_id, run_id, step_id, "skipped")
        clear_checkpoint(org_id, run_id, step_id)
        sys.exit(0)

    except Exception as exc:
        print(f"[email-drafter] FATAL: {exc}")
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
            print("[email-drafter] Failed to write error status to Firestore")
            traceback.print_exc()

        clear_checkpoint(org_id, run_id, step_id)
        sys.exit(1)


if __name__ == "__main__":
    main()
