"""Echo Step Agent — test/starter agent for pipeline validation.

Reads environment variables, echoes them back, and exits.
Used for CI/CD pipeline testing and step agent container lifecycle validation.
"""

import os
import sys


def main():
    step_id = os.environ.get("STEP_ID", "unknown")
    run_id = os.environ.get("RUN_ID", "unknown")
    org_id = os.environ.get("ORG_ID", "unknown")

    print(f"[step-echo] Step {step_id} for run {run_id} (org {org_id})")
    print("[step-echo] Echo agent completed successfully")
    sys.exit(0)


if __name__ == "__main__":
    main()
