"""Account Provisioner Step Agent — 2-phase HITL checkpoint/resume.

Phase 1 (fresh):  Load skill -> read context -> LLM generates provisioning plan -> request approval -> checkpoint -> pod exits
Phase 2 (resume): Read decision -> post Slack welcome + create Jira onboarding task -> write report -> complete

Uses Claude API for plan generation, Slack API for welcome messages, and Jira API for ticket creation.
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
    request_approval,
)
from step_agent.jira_client import create_issue
from step_agent.llm_client import generate
from step_agent.skill_loader import load_skill
from step_agent.slack_client import post_message
from step_agent.storage_tools import write_report


# ---------------------------------------------------------------------------
# Phase functions
# ---------------------------------------------------------------------------


def _phase_fresh(org_id: str, run_id: str, step_id: str) -> None:
    """Phase 1: LLM generates provisioning plan and requests IT approval."""
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
    new_hire = context.get("new_hire_name", "new hire")
    company = context.get("company_name", "Company")
    email = context.get("new_hire_email", "user@company.com")
    manager = context.get("manager_email", "manager@company.com")

    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={
            "message": f"Generating account provisioning plan for {new_hire}",
            "percent": 30,
        },
    )

    # LLM generates a tailored provisioning plan
    account_list = generate(
        org_id, run_id, step_id,
        system_prompt=(
            "You are an IT operations specialist responsible for new employee "
            "account provisioning. Generate a comprehensive, well-structured "
            "account provisioning plan in markdown format. Include a table of "
            "accounts to create, access groups, security configuration, and "
            "notification plan."
        ),
        user_prompt=(
            f"Generate an account provisioning plan for:\n"
            f"- New hire: {new_hire}\n"
            f"- Email: {email}\n"
            f"- Manager: {manager}\n"
            f"- Organization: {company}\n\n"
            f"Include accounts for: Google Workspace, Slack, Jira, GitHub, "
            f"1Password, and VPN. Use markdown tables. Include security "
            f"configuration (MFA, SSO) and notification plan."
        ),
        max_tokens=2048,
        temperature=0.5,
    )

    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": "Account list ready — requesting IT approval", "percent": 50},
    )

    # Request approval — this checkpoints and exits (never returns)
    request_approval(
        org_id, run_id, step_id,
        description="Please review the AI-generated account provisioning plan and approve to proceed.",
        draft_content=account_list,
        risk_level="medium",
        checkpoint_data={"account_list": account_list, "context": context},
    )
    # Pod exits here


def _phase_after_approval(
    org_id: str,
    run_id: str,
    step_id: str,
    decision: dict,
    checkpoint_data: dict,
) -> None:
    """Phase 2: post Slack welcome + create Jira task, write report, complete."""
    update_step_status(org_id, run_id, step_id, "running")
    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": "Resumed — processing IT approval decision", "percent": 75},
    )

    decision_value = decision.get("decision", "reject")
    account_list = checkpoint_data.get("account_list", "")
    context = checkpoint_data.get("context", {})
    new_hire = context.get("new_hire_name", "New Hire")
    company = context.get("company_name", "Company")
    email = context.get("new_hire_email", "")
    start_date = context.get("start_date", "TBD")
    slack_channel = context.get("slack_channel", "general")
    jira_project = context.get("jira_project", "HR")

    print(f"[account-provisioner] Approval decision: {decision_value}")

    write_event(
        org_id, run_id, "agent_tool_use",
        step_id=step_id,
        payload={
            "toolName": "request_approval",
            "args": {"riskLevel": "medium"},
            "result": f"Decision: {decision_value}",
        },
    )

    if decision_value not in ("approve", "revise"):
        # Rejected
        report = account_list + "\n---\n\n_Rejected by IT. No accounts will be created._\n"
        summary = "Account provisioning rejected by IT."

        result = write_report(
            org_id, run_id, step_id, report,
            title="account-provisioning.md",
            description="Account provisioning plan (rejected)",
        )
        print(f"[account-provisioner] Wrote report: {result['storagePath']}")

        clear_checkpoint(org_id, run_id, step_id)
        write_event(
            org_id, run_id, "step_completed",
            step_id=step_id,
            payload={"resultSummary": summary},
        )
        update_step_status(org_id, run_id, step_id, "completed", result_summary=summary)
        print(f"[account-provisioner] Step completed: {summary}")
        sys.exit(0)

    # Approved — execute API calls
    final_plan = decision.get("revisedContent") or account_list if decision_value == "revise" else account_list

    # Post Slack welcome message
    slack_result = {}
    slack_status = "skipped"
    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": f"Posting welcome message to Slack #{slack_channel}", "percent": 80},
    )
    try:
        # Normalize: accept "general" or "#general"
        channel_arg = slack_channel if slack_channel.startswith("#") else f"#{slack_channel}"
        slack_result = post_message(
            org_id,
            channel=channel_arg,
            text=f":wave: Welcome {new_hire} to {company}! They're joining us on {start_date}. Say hello! :tada:",
        )
        slack_status = f"posted (ts={slack_result.get('ts', '')})"
        write_event(
            org_id, run_id, "agent_tool_use",
            step_id=step_id,
            payload={
                "toolName": "slack_post_message",
                "args": {"channel": channel_arg},
                "result": "Welcome message posted",
            },
        )
        print(f"[account-provisioner] Slack posted: {slack_result}")
    except Exception as e:
        slack_status = f"failed: {e}"
        print(f"[account-provisioner] Slack failed (non-fatal): {e}")

    # Create Jira onboarding task
    jira_result = {}
    jira_status = "skipped"
    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": "Creating Jira onboarding task", "percent": 85},
    )
    try:
        jira_result = create_issue(
            org_id,
            project_key=jira_project,
            summary=f"Onboarding: {new_hire} — Account Setup & Provisioning",
            description=(
                f"Complete account provisioning and onboarding setup for {new_hire} "
                f"({email}) joining {company} on {start_date}.\n\n"
                f"Accounts to provision: Google Workspace, Slack, Jira, GitHub, "
                f"1Password, VPN.\n\nSee the provisioning plan artifact for details."
            ),
            labels=["onboarding", "provisioning"],
        )
        jira_status = f"created {jira_result.get('key', 'issue')}"
        write_event(
            org_id, run_id, "agent_tool_use",
            step_id=step_id,
            payload={
                "toolName": "jira_create_issue",
                "args": {"project": jira_project},
                "result": f"Created {jira_result.get('key', 'issue')}",
            },
        )
        print(f"[account-provisioner] Jira created: {jira_result}")
    except Exception as e:
        jira_status = f"failed: {e}"
        print(f"[account-provisioner] Jira failed (non-fatal): {e}")

    # Build final report
    status_label = "Revised and approved" if decision_value == "revise" else "Approved"
    report = final_plan + "\n\n---\n\n"
    report += "## API Integration Results\n\n"
    report += f"- Slack: {slack_status}\n"
    report += f"- Jira: {jira_status}\n"
    report += f"\n_{status_label} by IT._\n"

    write_event(
        org_id, run_id, "progress",
        step_id=step_id,
        payload={"message": "Writing provisioning report", "percent": 90},
    )

    result = write_report(
        org_id, run_id, step_id, report,
        title="account-provisioning.md",
        description="Account provisioning plan and API results",
    )
    print(f"[account-provisioner] Wrote report: {result['storagePath']}")

    clear_checkpoint(org_id, run_id, step_id)

    summary = f"Account provisioning approved. Slack: {slack_status}. Jira: {jira_status}."
    write_event(
        org_id, run_id, "step_completed",
        step_id=step_id,
        payload={"resultSummary": summary},
    )
    update_step_status(
        org_id, run_id, step_id, "completed",
        result_summary=summary,
    )
    print(f"[account-provisioner] Step completed: {summary}")
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
        print("[account-provisioner] ERROR: RUN_ID and ORG_ID env vars are required")
        sys.exit(1)

    print(f"[account-provisioner] Starting step={step_id} run={run_id} org={org_id}")
    if resume_thread_id:
        print(f"[account-provisioner] Resuming from checkpoint (thread={resume_thread_id})")

    try:
        if not resume_thread_id:
            _phase_fresh(org_id, run_id, step_id)
        else:
            checkpoint = load_checkpoint(org_id, run_id, step_id)
            if checkpoint is None:
                raise RuntimeError(
                    f"RESUME_THREAD_ID set but no checkpoint found for step {step_id}"
                )

            run_status = read_run_status(org_id, run_id)
            if run_status == "aborted":
                raise RunAbortedError("Run was aborted while step was paused")

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

            if phase == "waiting_for_approval":
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
        print("[account-provisioner] Run was aborted")
        update_step_status(org_id, run_id, step_id, "skipped")
        clear_checkpoint(org_id, run_id, step_id)
        sys.exit(0)

    except Exception as exc:
        print(f"[account-provisioner] FATAL: {exc}")
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
            print("[account-provisioner] Failed to write error status to Firestore")
            traceback.print_exc()

        clear_checkpoint(org_id, run_id, step_id)
        sys.exit(1)


if __name__ == "__main__":
    main()
