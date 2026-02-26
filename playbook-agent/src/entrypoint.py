"""Playbook Agent entrypoint — stub for Issue 2 scaffolding.

The full orchestration logic is implemented in Issue 8.
This validates that the container builds, starts, and can read env vars.
"""

import os
import sys


def main():
    run_id = os.environ.get("RUN_ID", "unknown")
    org_id = os.environ.get("ORG_ID", "unknown")
    playbook_id = os.environ.get("PLAYBOOK_ID", "unknown")

    print(f"[playbook-agent] Starting for run={run_id}, org={org_id}, playbook={playbook_id}")
    print("[playbook-agent] Stub entrypoint — orchestration not yet implemented (see Issue 8)")
    sys.exit(0)


if __name__ == "__main__":
    main()
