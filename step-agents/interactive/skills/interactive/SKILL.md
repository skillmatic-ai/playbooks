---
name: interactive
description: A test skill that demonstrates the HITL (human-in-the-loop) flow by asking a question, using the answer, and requesting approval on a draft.
---

# Interactive Skill

This skill validates the full interactive agent flow: question → answer → approval.

## Behavior

1. Ask the user a free-text question about project preferences
2. Use the answer to generate a draft document
3. Request approval on the generated draft
4. If approved, write the final report; if rejected, note the rejection

## Expected Environment

- `STEP_ID` - The step identifier within the playbook run
- `RUN_ID` - The playbook run identifier
- `ORG_ID` - The organization identifier

## Output

Writes a report to `/shared/results/{STEP_ID}/report.md` including the user's
answers and approval decision.
