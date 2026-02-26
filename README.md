# Skillmatic Playbooks

Public catalog of playbook definitions and step agent images for [Skillmatic](https://skillmatic.ai).

## Repository Structure

```
playbook-agent/         # Shared orchestrator Docker image (one image, reads any PLAYBOOK.md)
step-agents/            # Reusable step agent Docker images
  echo/                 # Test/starter step agent
playbooks/
  verified/             # Skillmatic-curated playbooks
  community/            # Community contributions (via PR)
scripts/
  sync-catalog.py       # CI/CD: syncs playbook catalog to Firestore
.github/workflows/      # CI/CD pipelines
```

## How It Works

1. **Playbook authors** create a `PLAYBOOK.md` file (v2 format with YAML frontmatter) in `playbooks/verified/` or `playbooks/community/`
2. **CI/CD** automatically:
   - Parses the PLAYBOOK.md and validates its structure
   - Syncs the catalog entry to the global Firestore `playbook_catalog/` collection
3. **Users** browse the catalog in the Skillmatic desktop app, install playbooks to their org, and launch them
4. **Agent images** are built and pushed to GCP Artifact Registry when source code changes

## Playbook Format (v2)

Playbooks use Markdown with YAML frontmatter:

```markdown
---
name: "My Playbook"
version: "1.0.0"
description: "What this playbook does"
category: Operations
schemaVersion: v2

trigger:
  type: human_initiation
  role: Admin

steps:
  - id: step-one
    order: 1
    title: "First Step"
    assignedRole: Engineering
    agentImage: skillmatic/step-echo:latest
    approval: approve_only
---

# My Playbook

Detailed instructions for each step...
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full format reference.

## Step Agents

Step agents are Docker images that execute individual playbook steps. Each contains:
- A `SKILL.md` following the [Agent Skills](https://agentskills.io) standard
- An entrypoint that reads the skill instructions and executes using an LLM
- Tools for Firestore communication, file operations, and Firebase Storage uploads

## Tracks

| Track | Directory | Review | Description |
|---|---|---|---|
| Verified | `playbooks/verified/` | Skillmatic team | Curated, tested, production-ready |
| Community | `playbooks/community/` | PR review | Community contributions |

## License

Copyright 2026 Skillmatic AI. All rights reserved.
