"""Calendar Manager Step Agent — single-phase, non-interactive.

Runs straight through: load skill -> read context -> LLM generates structured meeting
schedule -> create real Google Calendar events -> write report -> complete.
No HITL pauses. Uses exception_only approval.

Uses Claude API for generating a meeting schedule as structured JSON,
then creates actual events via the Google Calendar API v3.
"""

import json
import os
import sys
import traceback

from step_agent.firestore_client import (
    read_run_context,
    read_run_status,
    update_step_status,
    write_event,
)
from step_agent.gcal_client import batch_create_events
from step_agent.hitl_tools import RunAbortedError
from step_agent.llm_client import generate
from step_agent.skill_loader import load_skill
from step_agent.storage_tools import write_report


def _parse_events_json(raw: str) -> list[dict]:
    """Extract JSON array from LLM output (may be wrapped in markdown fences)."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


def main() -> None:
    run_id = os.environ.get("RUN_ID")
    org_id = os.environ.get("ORG_ID")
    step_id = os.environ.get("STEP_ID", "unknown")

    if not run_id or not org_id:
        print("[calendar-manager] ERROR: RUN_ID and ORG_ID env vars are required")
        sys.exit(1)

    print(f"[calendar-manager] Starting step={step_id} run={run_id} org={org_id}")

    try:
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
        new_hire_email = context.get("new_hire_email", "")
        company = context.get("company_name", "Company")
        manager = context.get("manager_email", "manager@company.com")
        start_date = context.get("start_date", "TBD")

        write_event(
            org_id, run_id, "progress",
            step_id=step_id,
            payload={
                "message": f"Generating meeting schedule for {new_hire} with AI",
                "percent": 20,
            },
        )

        # LLM generates structured JSON events
        events_json_raw = generate(
            org_id, run_id, step_id,
            system_prompt=(
                "You are an HR operations expert. Generate a week-1 onboarding meeting "
                "schedule as a JSON array. Each event object must have exactly these fields:\n"
                '  "summary": string (meeting title),\n'
                '  "start": string (ISO 8601 datetime, e.g. "2025-04-01T09:00:00"),\n'
                '  "end": string (ISO 8601 datetime),\n'
                '  "description": string (brief description),\n'
                '  "location": string (room name or "Virtual"),\n'
                '  "attendees": array of email strings\n\n'
                "Output ONLY the JSON array, no markdown, no explanation."
            ),
            user_prompt=(
                f"Create 12-15 onboarding meetings for week 1:\n"
                f"- New hire: {new_hire} ({new_hire_email})\n"
                f"- Start date (Monday): {start_date}\n"
                f"- Manager: {manager}\n"
                f"- Organization: {company}\n\n"
                f"Include: Monday orientation + IT setup + team lunch, "
                f"Tuesday manager 1:1 + project overview, "
                f"Wednesday HR benefits + codebase walkthrough, "
                f"Thursday standup + security training + pair programming, "
                f"Friday retrospective + cross-team intros + social mixer.\n\n"
                f"Use realistic times (9am-5pm). Attendees should include "
                f"{new_hire_email} plus relevant people (use generic emails like "
                f"hr@{company.lower().replace(' ', '')}.com for HR, etc)."
            ),
            max_tokens=3000,
            temperature=0.4,
        )

        events = _parse_events_json(events_json_raw)
        print(f"[calendar-manager] LLM generated {len(events)} events")

        write_event(
            org_id, run_id, "progress",
            step_id=step_id,
            payload={
                "message": f"Creating {len(events)} Google Calendar events",
                "percent": 45,
            },
        )

        # Create real Google Calendar events
        gcal_results = batch_create_events(org_id, events)
        print(f"[calendar-manager] Created {len(gcal_results)} calendar events")

        write_event(
            org_id, run_id, "agent_tool_use",
            step_id=step_id,
            payload={
                "toolName": "gcal_batch_create",
                "args": {"count": len(events)},
                "result": f"{len(gcal_results)} events created",
            },
        )

        write_event(
            org_id, run_id, "progress",
            step_id=step_id,
            payload={"message": "Generating schedule report", "percent": 70},
        )

        # LLM generates human-readable report
        schedule_report = generate(
            org_id, run_id, step_id,
            system_prompt=(
                "You are an HR operations expert. Generate a beautifully formatted "
                "markdown meeting schedule from the provided event data. Include "
                "a table with Day, Time, Meeting, Attendees, Duration, and Location columns. "
                "Add a key contacts table and calendar setup notes at the end."
            ),
            user_prompt=(
                f"Format this week-1 onboarding schedule for {new_hire} at {company} "
                f"(starting {start_date}, manager: {manager}).\n\n"
                f"Events data:\n{json.dumps(events, indent=2)}\n\n"
                f"All {len(gcal_results)} events were created in Google Calendar.\n\n"
                f"Include a key contacts table and notes about calendar reminders."
            ),
            max_tokens=3000,
            temperature=0.5,
        )

        # Append calendar links
        schedule_report += "\n\n---\n\n## Google Calendar Events\n\n"
        for i, r in enumerate(gcal_results):
            evt_name = events[i].get("summary", "Unknown") if i < len(events) else "Unknown"
            schedule_report += f"- {evt_name}: [Open in Calendar]({r.get('htmlLink', '#')})\n"

        result = write_report(
            org_id, run_id, step_id, schedule_report,
            title="meeting-schedule.md",
            description="Week 1 onboarding meeting schedule with Google Calendar links",
        )
        print(f"[calendar-manager] Wrote report: {result['storagePath']}")

        summary = f"Onboarding schedule created for {new_hire}. {len(gcal_results)} meetings added to Google Calendar."
        write_event(
            org_id, run_id, "step_completed",
            step_id=step_id,
            payload={"resultSummary": summary},
        )
        update_step_status(
            org_id, run_id, step_id, "completed",
            result_summary=summary,
        )
        print(f"[calendar-manager] Step completed: {summary}")
        sys.exit(0)

    except SystemExit:
        raise

    except RunAbortedError:
        print("[calendar-manager] Run was aborted")
        update_step_status(org_id, run_id, step_id, "skipped")
        sys.exit(0)

    except Exception as exc:
        print(f"[calendar-manager] FATAL: {exc}")
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
            print("[calendar-manager] Failed to write error status to Firestore")
            traceback.print_exc()

        sys.exit(1)


if __name__ == "__main__":
    main()
