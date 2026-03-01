"""Report Generator Step Agent — single-phase, reads sibling step data from Firestore.

Runs straight through: load skill -> read context -> read all step results -> LLM compiles narrative report -> upload -> complete.
No HITL pauses. This step runs last, after schedule-meetings completes.

Uses read_all_step_results() and read_all_files() to aggregate data from
sibling steps via Firestore (since each pod has ephemeral emptyDir storage).
Uses Claude API to compile a narrative executive report from the aggregated data.
"""

import os
import sys
import traceback

from step_agent.firestore_client import (
    read_all_files,
    read_all_step_results,
    read_run_context,
    read_run_status,
    update_step_status,
    write_event,
)
from step_agent.hitl_tools import RunAbortedError
from step_agent.llm_client import generate
from step_agent.skill_loader import load_skill
from step_agent.storage_tools import write_report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    run_id = os.environ.get("RUN_ID")
    org_id = os.environ.get("ORG_ID")
    step_id = os.environ.get("STEP_ID", "unknown")

    if not run_id or not org_id:
        print("[report-generator] ERROR: RUN_ID and ORG_ID env vars are required")
        sys.exit(1)

    print(f"[report-generator] Starting step={step_id} run={run_id} org={org_id}")

    try:
        # Check for abort before starting
        run_status = read_run_status(org_id, run_id)
        if run_status == "aborted":
            raise RunAbortedError("Run was aborted before step started")

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
        email = context.get("new_hire_email", "")
        manager = context.get("manager_email", "")
        start_date = context.get("start_date", "TBD")

        write_event(
            org_id, run_id, "progress",
            step_id=step_id,
            payload={
                "message": f"Reading results from all previous steps for {new_hire}",
                "percent": 20,
            },
        )

        # Read sibling step data from Firestore
        all_steps = read_all_step_results(org_id, run_id)
        all_files = read_all_files(org_id, run_id)

        # Exclude self from report inputs
        prev_steps = [s for s in all_steps if s.get("id") != step_id]

        write_event(
            org_id, run_id, "progress",
            step_id=step_id,
            payload={
                "message": f"Compiling report from {len(prev_steps)} steps and {len(all_files)} artifacts with AI",
                "percent": 40,
            },
        )

        # Build structured data for the LLM
        steps_summary = ""
        for step in prev_steps:
            sid = step.get("id", "unknown")
            title = step.get("title", sid)
            status = step.get("status", "unknown")
            result_summary = step.get("resultSummary", "No summary available.")
            error = step.get("error", {})
            steps_summary += f"\n### {title}\n- Status: {status}\n- Summary: {result_summary}\n"
            if error:
                steps_summary += f"- Error: {error.get('message', 'Unknown')}\n"

        files_summary = ""
        if all_files:
            files_summary = "\n## Generated Artifacts\n"
            for f in all_files:
                fname = f.get("name", "unknown")
                fstep = f.get("stepId", "")
                ftype = f.get("mimeType", "")
                fsize = f.get("sizeBytes", 0)
                files_summary += f"- {fname} (step: {fstep}, type: {ftype}, size: {fsize:,} bytes)\n"

        completed_count = sum(1 for s in prev_steps if s.get("status") == "completed")
        total_count = len(prev_steps)

        # LLM compiles narrative report
        report = generate(
            org_id, run_id, step_id,
            system_prompt=(
                "You are an HR operations analyst compiling an executive onboarding "
                "report. Write a comprehensive, professional report in markdown format. "
                "Include an executive summary, detailed step-by-step analysis, "
                "generated artifacts table, action items for day one, and an IT checklist. "
                "Be specific and reference actual data from the step results. "
                "The tone should be professional and actionable."
            ),
            user_prompt=(
                f"Compile an onboarding report for:\n"
                f"- New hire: {new_hire} ({email})\n"
                f"- Organization: {company}\n"
                f"- Manager: {manager}\n"
                f"- Start date: {start_date}\n"
                f"- Completion: {completed_count}/{total_count} steps completed\n\n"
                f"## Step Results\n{steps_summary}\n"
                f"{files_summary}\n\n"
                f"Write the report with these sections:\n"
                f"1. Executive Summary (overall readiness assessment)\n"
                f"2. Step-by-Step Results (detailed analysis of each step)\n"
                f"3. Generated Artifacts (table format)\n"
                f"4. Next Steps for {new_hire}'s First Day (numbered list)\n"
                f"5. IT Checklist (checkbox format)\n"
                f"6. Footer with generation metadata"
            ),
            max_tokens=4096,
            temperature=0.5,
        )

        write_event(
            org_id, run_id, "progress",
            step_id=step_id,
            payload={
                "message": "Onboarding report compiled — uploading artifact",
                "percent": 80,
            },
        )

        result = write_report(
            org_id, run_id, step_id, report,
            title="onboarding-report.md",
            description="AI-generated comprehensive onboarding summary report",
        )
        print(f"[report-generator] Wrote report: {result['storagePath']}")

        summary = (
            f"AI-generated onboarding report for {new_hire}. "
            f"Compiled {len(prev_steps)} step results and {len(all_files)} artifacts "
            f"into a comprehensive executive summary."
        )
        write_event(
            org_id, run_id, "step_completed",
            step_id=step_id,
            payload={"resultSummary": summary},
        )
        update_step_status(
            org_id, run_id, step_id, "completed",
            result_summary=summary,
        )
        print(f"[report-generator] Step completed: {summary}")
        sys.exit(0)

    except SystemExit:
        raise

    except RunAbortedError:
        print("[report-generator] Run was aborted")
        update_step_status(org_id, run_id, step_id, "skipped")
        sys.exit(0)

    except Exception as exc:
        print(f"[report-generator] FATAL: {exc}")
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
            print("[report-generator] Failed to write error status to Firestore")
            traceback.print_exc()

        sys.exit(1)


if __name__ == "__main__":
    main()
