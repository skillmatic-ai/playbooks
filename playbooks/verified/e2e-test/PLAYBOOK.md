---
name: "E2E Pipeline Test"
version: "1.0.0"
description: "End-to-end test playbook that exercises the echo agent (non-interactive) and the interactive agent (HITL checkpoint/resume)."
category: "testing"
schemaVersion: "v2"

trigger:
  type: manual

participants:
  - role: tester
    minCount: 1

variables:
  - name: project_name
    source: "triggerInputs.project_name"
    required: false
    description: "Optional project name passed at launch"

steps:
  - id: echo-step
    order: 1
    title: "Echo Context"
    assignedRole: tester
    agentImage: echo
    timeoutMinutes: 10
    interactive: false
    approval: approve_only

  - id: interactive-step
    order: 2
    title: "Interactive Summary"
    assignedRole: tester
    agentImage: interactive
    timeoutMinutes: 30
    interactive: true
    approval: approve_only
---

# E2E Pipeline Test Playbook

This playbook validates the full Skillmatic agentic pipeline.

## Step: echo-step

The echo agent loads its skill, reads the hydrated run context, and writes
a report to `/shared/results/echo-step/report.md`. This step completes
without any human interaction — it tests the basic orchestrator → step
agent → Firestore lifecycle.

## Step: interactive-step

The interactive agent demonstrates the checkpoint/resume HITL flow:

1. **Phase 1** — Asks the user a free-text question, then checkpoints and
   the pod terminates.
2. **Phase 2** — On resume, reads the user's answer, generates a draft
   document, requests approval, then checkpoints and the pod terminates
   again.
3. **Phase 3** — On resume, reads the approval decision and writes the
   final report.

This step tests `onInputReceived`, resume K8s Jobs, and multi-phase
checkpoint/resume.
