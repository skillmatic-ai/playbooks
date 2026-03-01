"""Playbook Agent entrypoint — parses PLAYBOOK.md, hydrates template variables,
and orchestrates step execution.

Lifecycle: startup → parse → hydrate → orchestrate steps → complete/fail
"""

import os
import sys
import traceback

from src.firestore_client import (
    build_hydration_context,
    update_run_status,
    write_event,
    _get_db,
)
from src.hydration import hydrate_playbook
from src.k8s_client import delete_configmap
from src.dag_scheduler import CyclicDependencyError
from src.orchestrator import RunAbortedError, StepFailedError, run_orchestration
from src.playbook_parser import parse_playbook_file

from firebase_admin import firestore as fs

PLAYBOOK_PATH = "/playbook/PLAYBOOK.md"
HYDRATED_OUTPUT_PATH = "/shared/PLAYBOOK_HYDRATED.md"


def main() -> None:
    run_id = os.environ.get("RUN_ID")
    org_id = os.environ.get("ORG_ID")
    playbook_id = os.environ.get("PLAYBOOK_ID", "unknown")

    if not run_id or not org_id:
        print("[playbook-agent] ERROR: RUN_ID and ORG_ID env vars are required")
        sys.exit(1)

    print(f"[playbook-agent] Starting run={run_id} org={org_id} playbook={playbook_id}")

    try:
        # ---- Mark run as running ----
        update_run_status(org_id, run_id, "running")
        write_event(
            org_id, run_id, "playbook_started",
            payload={"playbookId": playbook_id},
        )
        print("[playbook-agent] Wrote playbook_started event")

        # ---- Parse PLAYBOOK.md ----
        playbook = parse_playbook_file(PLAYBOOK_PATH)
        write_event(org_id, run_id, "progress", payload={
            "message": (
                f"Parsed playbook: {playbook.name} v{playbook.version} "
                f"({len(playbook.steps)} steps, {len(playbook.variables)} variables)"
            ),
        })
        print(
            f"[playbook-agent] Parsed: {playbook.name} v{playbook.version} "
            f"— {len(playbook.steps)} steps, {len(playbook.variables)} variables"
        )

        # ---- Fetch context + hydrate template ----
        context = build_hydration_context(org_id, run_id, playbook.variables)
        resolved = hydrate_playbook(playbook, context, HYDRATED_OUTPUT_PATH)
        write_event(org_id, run_id, "progress", payload={
            "message": f"Template hydration complete: {len(resolved)} variables resolved",
            "hydratedVariables": resolved,
        })
        print(f"[playbook-agent] Hydrated {len(resolved)} variables → {HYDRATED_OUTPUT_PATH}")

        # Update run doc with hydrated context
        db = _get_db()
        db.collection("orgs").document(org_id) \
            .collection("playbook_runs").document(run_id) \
            .update({"context": resolved, "updatedAt": fs.SERVER_TIMESTAMP})

        # ---- Orchestrate steps ----
        namespace = os.environ.get("NAMESPACE", "skillmatic")

        run_orchestration(playbook, org_id, run_id, namespace)

        # ---- Mark run as completed ----
        step_count = len(playbook.steps)
        summary = f"All {step_count} steps completed successfully."
        write_event(
            org_id, run_id, "playbook_completed",
            payload={"summary": summary},
        )
        update_run_status(org_id, run_id, "completed", summary=summary)
        print(f"[playbook-agent] Run completed: {summary}")

        # Clean up ConfigMap (best-effort — Jobs auto-clean via TTL)
        _cleanup_configmap(run_id)
        sys.exit(0)

    except RunAbortedError:
        # Run was aborted by user — status already set to "aborted" by Firebase Function.
        # Just clean up and exit cleanly.
        print("[playbook-agent] Run aborted — cleaning up and exiting")
        _cleanup_configmap(run_id)
        sys.exit(0)

    except CyclicDependencyError as exc:
        print(f"[playbook-agent] FATAL: {exc}")
        try:
            write_event(
                org_id, run_id, "playbook_failed",
                payload={"error": str(exc)},
            )
            update_run_status(
                org_id, run_id, "failed",
                error={"code": "CYCLIC_DEPENDENCY", "message": str(exc)},
            )
        except Exception:
            print("[playbook-agent] Failed to write error status to Firestore")
            traceback.print_exc()

        _cleanup_configmap(run_id)
        sys.exit(1)

    except Exception as exc:
        print(f"[playbook-agent] FATAL: {exc}")
        traceback.print_exc()

        try:
            write_event(
                org_id, run_id, "playbook_failed",
                payload={"error": str(exc)},
            )
            update_run_status(
                org_id, run_id, "failed",
                error={"code": "AGENT_CRASH", "message": str(exc)},
            )
        except Exception:
            print("[playbook-agent] Failed to write error status to Firestore")
            traceback.print_exc()

        _cleanup_configmap(run_id)
        sys.exit(1)


def _cleanup_configmap(run_id: str) -> None:
    """Delete the playbook ConfigMap (best-effort)."""
    try:
        cm_name = f"playbook-{run_id.lower()}"
        delete_configmap(cm_name)
        print(f"[playbook-agent] Deleted ConfigMap {cm_name}")
    except Exception:
        print("[playbook-agent] ConfigMap cleanup failed (non-fatal)")


if __name__ == "__main__":
    main()
