---
id: "e2e-test"
name: "E2E Pipeline Test"
version: "2.0.0"
description: "End-to-end test playbook that exercises DAG parallel scheduling, echo agents, and interactive HITL checkpoint/resume."
category: "testing"
schemaVersion: "v2"

trigger:
  type: human_initiation
  role: tester

participants:
  - role: tester
    minCount: 1

variables:
  - name: project_name
    source: "triggerInputs.project_name"
    required: false
    description: "Optional project name passed at launch"

steps:
  - id: echo-alpha
    order: 1
    title: "Echo Alpha"
    assignedRole: tester
    agentImage: echo
    timeoutMinutes: 10
    interactive: false
    approval: approve_only
    dependencies: []

  - id: echo-beta
    order: 2
    title: "Echo Beta"
    assignedRole: tester
    agentImage: echo
    timeoutMinutes: 10
    interactive: false
    approval: approve_only
    dependencies: []

  - id: interactive-step
    order: 3
    title: "Interactive Summary"
    assignedRole: tester
    agentImage: interactive
    timeoutMinutes: 30
    interactive: true
    approval: approve_only
    dependencies: [echo-alpha, echo-beta]
---

# E2E Pipeline Test Playbook

This playbook validates the full Skillmatic agentic pipeline including
DAG-aware parallel step scheduling.

## Step: echo-alpha

The first echo agent runs in parallel with echo-beta (no dependencies).
Loads its skill, reads the hydrated run context, and writes a report to
`/shared/results/echo-alpha/report.md`. Tests the basic orchestrator →
step agent → Firestore lifecycle.

## Step: echo-beta

The second echo agent runs in parallel with echo-alpha (no dependencies).
Same behavior — loads skill, reads context, writes report. Together with
echo-alpha, validates that the orchestrator launches independent steps
concurrently.

## Step: interactive-step

Depends on both echo-alpha and echo-beta. Only starts after both complete.
Demonstrates the checkpoint/resume HITL flow:

1. **Phase 1** — Asks the user a free-text question, then checkpoints and
   the pod terminates.
2. **Phase 2** — On resume, reads the user's answer, generates a draft
   document, requests approval, then checkpoints and the pod terminates
   again.
3. **Phase 3** — On resume, reads the approval decision and writes the
   final report.

This step tests `onInputReceived`, resume K8s Jobs, multi-phase
checkpoint/resume, and DAG dependency gating.
