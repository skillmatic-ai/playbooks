---
name: echo
description: A test skill that echoes received input. Used for CI/CD pipeline validation and step agent container lifecycle testing.
---

# Echo Skill

This is a test/starter skill for validating the Skillmatic step agent pipeline.

## Behavior

1. Read any input provided via environment variables or context
2. Echo the input back as a structured report
3. Write the report to the shared results directory

## Expected Environment

- `STEP_ID` - The step identifier within the playbook run
- `RUN_ID` - The playbook run identifier
- `ORG_ID` - The organization identifier

## Output

Writes a plain text report to `/shared/results/{STEP_ID}/report.md` echoing back
the inputs received.
