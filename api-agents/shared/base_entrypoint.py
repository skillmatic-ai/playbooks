"""base_entrypoint.py — Standard lifecycle entrypoint for all API agents.

Each API agent image inherits this entrypoint.  The specific agent provides
an ``execute()`` function that receives the prepared context (token, skills,
prior reports) and performs the actual work.

Lifecycle:
  1. Read env vars: RUN_ID, ORG_ID, STEP_ID, RESUME_THREAD_ID
  2. Initialize Firebase Admin
  3. Read step config from Firestore (api, skills, role)
  4. Load OAuth token for the assigned user
  5. Fetch task skills from skills_catalog/
  6. Load base skill from /base-skill/ (baked into the agent image)
  7. Read prior reports (if depends_on)
  8. If RESUME_THREAD_ID: load checkpoint, read input, resume
  9. Else: invoke agent with combined instructions
  10. Write report + artifacts on completion
  11. Update step status to completed

Usage (in an API agent's Dockerfile):
    ENV AGENT_MODULE=agent.main
    ENTRYPOINT ["python", "-m", "base_entrypoint"]

The AGENT_MODULE env var points to a Python module that exports:
    execute(ctx: AgentContext) -> AgentResult
    resume(ctx: AgentContext, checkpoint: dict, user_input: dict) -> AgentResult
"""

from __future__ import annotations

import importlib
import os
import sys
import traceback
from dataclasses import dataclass, field

from checkpoint import clear_checkpoint, load_checkpoint
from context_reader import read_prior_reports
from firestore_client import (
    read_input,
    read_run_status,
    read_step_config,
    update_step_status,
    write_event,
)
from report_writer import emit_artifact_events, write_report
from skill_composer import compose_instructions
from skill_fetcher import SkillContent, fetch_skills, format_skills_prompt
from token_reader import get_access_token, has_token


# ---------------------------------------------------------------------------
# Agent context — passed to the agent's execute() function
# ---------------------------------------------------------------------------


@dataclass
class AgentContext:
    """Everything an API agent needs to do its work."""
    org_id: str
    run_id: str
    step_id: str
    api: str                          # e.g. "notion", "zendesk", "github"
    access_token: str                 # OAuth access token for the target API
    skills: list[SkillContent]        # Task skills fetched from catalog
    skills_prompt: str                # Formatted skills text for LLM prompt
    base_skill_prompt: str            # Baked-in API reference from /base-skill/
    prior_reports: str                # Reports from dependency steps
    composed_instructions: str        # Combined base + task skills + reports
    step_config: dict                 # Full step document from Firestore
    run_context: dict                 # Hydrated playbook variables


@dataclass
class AgentResult:
    """Output from an API agent's execute() or resume() function."""
    report_markdown: str = ""
    artifacts: list[dict] = field(default_factory=list)
    result_summary: str = ""


# ---------------------------------------------------------------------------
# Base skill loader
# ---------------------------------------------------------------------------


def _load_base_skill() -> str:
    """Load the agent's base skill from /base-skill/SKILL.md (baked into image)."""
    skill_path = "/base-skill/SKILL.md"
    try:
        with open(skill_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print("[entrypoint] No base skill found at /base-skill/SKILL.md")
        return ""


# ---------------------------------------------------------------------------
# Agent module loader
# ---------------------------------------------------------------------------


def _load_agent_module():
    """Import the agent module specified by AGENT_MODULE env var."""
    module_name = os.environ.get("AGENT_MODULE", "agent.main")
    try:
        return importlib.import_module(module_name)
    except ImportError as e:
        print(f"[entrypoint] Failed to import agent module '{module_name}': {e}")
        raise


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    """Standard API agent lifecycle."""
    # 1. Read env vars
    org_id = os.environ.get("ORG_ID", "")
    run_id = os.environ.get("RUN_ID", "")
    step_id = os.environ.get("STEP_ID", "")
    resume_thread_id = os.environ.get("RESUME_THREAD_ID", "")

    if not org_id or not run_id or not step_id:
        print("[entrypoint] ERROR: ORG_ID, RUN_ID, STEP_ID env vars required")
        sys.exit(1)

    print(f"[entrypoint] Starting: org={org_id} run={run_id} step={step_id}")

    try:
        # 2. Read step config from Firestore
        step_config = read_step_config(org_id, run_id, step_id)
        api = step_config.get("api", "")
        skill_ids = step_config.get("skills", [])
        assigned_uid = step_config.get("assignedUid", "")

        print(f"[entrypoint] API: {api}, skills: {skill_ids}")

        # 3. Load OAuth token
        access_token = ""
        if api and assigned_uid:
            if await_token_check(org_id, assigned_uid, api):
                access_token = get_access_token_sync(org_id, assigned_uid, api)
                print(f"[entrypoint] OAuth token loaded for {api}")
            else:
                print(f"[entrypoint] WARNING: No OAuth token for {api}")

        # 4. Fetch task skills
        skills = fetch_skills(skill_ids, agent_api=api) if skill_ids else []
        skills_prompt = format_skills_prompt(skills)

        # Emit progress event for loaded skills
        if skills:
            skill_names = [s.name for s in skills]
            write_event(
                org_id, run_id, "progress",
                step_id=step_id,
                payload={
                    "message": f"Loaded {len(skills)} task skill{'s' if len(skills) != 1 else ''}: {', '.join(skill_names)}",
                    "skillIds": skill_ids,
                    "skillNames": skill_names,
                },
            )
            print(f"[entrypoint] Loaded {len(skills)} task skills: {', '.join(skill_names)}")

        # 5. Load base skill
        base_skill_prompt = _load_base_skill()

        # 6. Read prior reports
        prior_reports = read_prior_reports(org_id, run_id, step_id)

        # 7. Compose unified instructions
        composed = compose_instructions(base_skill_prompt, skills, prior_reports)

        # 8. Build context
        from firestore_client import read_run_context
        run_context = read_run_context(org_id, run_id)

        ctx = AgentContext(
            org_id=org_id,
            run_id=run_id,
            step_id=step_id,
            api=api,
            access_token=access_token,
            skills=skills,
            skills_prompt=skills_prompt,
            base_skill_prompt=base_skill_prompt,
            prior_reports=prior_reports,
            composed_instructions=composed,
            step_config=step_config,
            run_context=run_context,
        )

        # 8. Load agent module
        agent_module = _load_agent_module()

        # 9. Execute or resume
        if resume_thread_id:
            print(f"[entrypoint] Resuming from checkpoint (thread={resume_thread_id})")
            checkpoint = load_checkpoint(org_id, run_id, step_id)
            if checkpoint is None:
                print("[entrypoint] WARNING: No checkpoint found, starting fresh")
                result = agent_module.execute(ctx)
            else:
                question_id = checkpoint.get("questionId", "")
                user_input = read_input(org_id, run_id, question_id) if question_id else None
                clear_checkpoint(org_id, run_id, step_id)
                result = agent_module.resume(ctx, checkpoint, user_input or {})
        else:
            result = agent_module.execute(ctx)

        # 10. Write report + artifacts
        if result.report_markdown:
            write_report(
                org_id, run_id, step_id,
                result.report_markdown,
                artifacts=result.artifacts,
            )
            print(f"[entrypoint] Report written: {len(result.report_markdown)} chars")

        if result.artifacts:
            emit_artifact_events(org_id, run_id, step_id, result.artifacts)
            print(f"[entrypoint] Emitted {len(result.artifacts)} artifact events")

        # 11. Mark step completed
        update_step_status(
            org_id, run_id, step_id, "completed",
            result_summary=result.result_summary or "Step completed successfully",
        )
        write_event(
            org_id, run_id, "step_completed",
            step_id=step_id,
            payload={
                "stepId": step_id,
                "resultSummary": result.result_summary,
                "hasReport": bool(result.report_markdown),
                "artifactCount": len(result.artifacts),
            },
        )
        print("[entrypoint] Step completed successfully")

    except SystemExit:
        # HITL pause — pod terminates cleanly (ask_user/request_approval called sys.exit(0))
        raise
    except Exception as e:
        # Unexpected failure
        error_msg = f"{type(e).__name__}: {e}"
        print(f"[entrypoint] FATAL: {error_msg}")
        traceback.print_exc()

        update_step_status(
            org_id, run_id, step_id, "failed",
            error={"code": "AGENT_ERROR", "message": error_msg},
        )
        write_event(
            org_id, run_id, "step_failed",
            step_id=step_id,
            payload={"stepId": step_id, "error": error_msg},
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Sync wrappers for async token_reader functions
# ---------------------------------------------------------------------------


def await_token_check(org_id: str, uid: str, service: str) -> bool:
    """Synchronous wrapper for has_token (which is async in token_reader)."""
    import asyncio
    return asyncio.run(has_token(org_id, uid, service))


def get_access_token_sync(org_id: str, uid: str, service: str) -> str:
    """Synchronous wrapper for get_access_token (which is async in token_reader)."""
    import asyncio
    return asyncio.run(get_access_token(org_id, uid, service))


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
