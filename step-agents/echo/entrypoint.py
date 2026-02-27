"""Echo Step Agent entrypoint — loads SKILL.md, reads context, writes echo report.

Lifecycle: startup → load skill → read context → execute → write report → complete
"""

import os
import sys
import traceback

from step_agent.firestore_client import update_step_status, write_event, read_run_context
from step_agent.skill_loader import load_skill
from step_agent.file_tools import write_report


def main() -> None:
    run_id = os.environ.get("RUN_ID")
    org_id = os.environ.get("ORG_ID")
    step_id = os.environ.get("STEP_ID", "unknown")

    if not run_id or not org_id:
        print("[step-agent] ERROR: RUN_ID and ORG_ID env vars are required")
        sys.exit(1)

    print(f"[step-agent] Starting step={step_id} run={run_id} org={org_id}")

    try:
        # ---- Mark step as running ----
        update_step_status(org_id, run_id, step_id, "running")
        write_event(
            org_id, run_id, "step_started",
            step_id=step_id,
            payload={"stepId": step_id},
        )
        print("[step-agent] Wrote step_started event")

        # ---- Load SKILL.md ----
        skill = load_skill("/app/skills")
        write_event(
            org_id, run_id, "progress",
            step_id=step_id,
            payload={"message": f"Loaded skill: {skill.name}"},
        )
        write_event(
            org_id, run_id, "log",
            step_id=step_id,
            payload={"message": f"Skill description: {skill.description}"},
        )
        print(f"[step-agent] Loaded skill: {skill.name} — {skill.description}")

        # ---- Read hydrated context ----
        write_event(
            org_id, run_id, "agent_thinking",
            step_id=step_id,
            payload={"thought": "Reading hydrated context from playbook run..."},
        )
        context = read_run_context(org_id, run_id)
        write_event(
            org_id, run_id, "agent_tool_use",
            step_id=step_id,
            payload={
                "toolName": "read_run_context",
                "args": {"orgId": org_id, "runId": run_id},
                "result": f"Read {len(context)} context variables",
            },
        )
        print(f"[step-agent] Read context: {len(context)} variables")

        # ---- Execute skill (echo: build report from context) ----
        write_event(
            org_id, run_id, "agent_thinking",
            step_id=step_id,
            payload={"thought": "Building echo report from context variables..."},
        )
        write_event(
            org_id, run_id, "progress",
            step_id=step_id,
            payload={"message": "Building report", "percent": 25},
        )

        report_lines = [
            f"# Echo Report — Step {step_id}",
            "",
            f"**Skill:** {skill.name}",
            f"**Run ID:** {run_id}",
            f"**Org ID:** {org_id}",
            "",
            "## Hydrated Context",
            "",
        ]

        if context:
            for key, value in sorted(context.items()):
                report_lines.append(f"- **{key}**: {value}")
        else:
            report_lines.append("_No context variables found._")

        report_lines.extend([
            "",
            "## Environment",
            "",
            f"- STEP_ID: `{step_id}`",
            f"- RUN_ID: `{run_id}`",
            f"- ORG_ID: `{org_id}`",
            f"- NAMESPACE: `{os.environ.get('NAMESPACE', 'unknown')}`",
            "",
            "---",
            "",
            "_Echo agent completed successfully._",
        ])

        report_content = "\n".join(report_lines)

        write_event(
            org_id, run_id, "progress",
            step_id=step_id,
            payload={"message": "Report built, writing to shared storage", "percent": 75},
        )

        # ---- Write report ----
        report_path = write_report(step_id, report_content)
        write_event(
            org_id, run_id, "agent_tool_use",
            step_id=step_id,
            payload={
                "toolName": "write_report",
                "args": {"stepId": step_id},
                "result": f"Report written to {report_path} ({len(report_content)} chars)",
            },
        )
        print(f"[step-agent] Wrote report to {report_path}")

        # ---- Mark step as completed ----
        summary = f"Echo skill completed. {len(context)} context variables echoed."
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

        sys.exit(1)


if __name__ == "__main__":
    main()
