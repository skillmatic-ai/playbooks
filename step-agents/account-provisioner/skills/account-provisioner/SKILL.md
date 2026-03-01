---
name: account-provisioner
description: AI-powered account provisioning with Slack welcome and Jira task creation. Uses Claude for plan generation and real API integrations. Supports approve-only approval with 2-phase checkpoint/resume.
---

# Account Provisioner Skill

Uses Claude API to generate a tailored account provisioning plan for new hires.
On approval, posts a welcome message to Slack and creates a Jira onboarding
task. Supports a 2-phase HITL workflow: AI plan generation with IT approval,
then API execution.

## Behavior

1. LLM generates a tailored account provisioning plan
2. Submit the AI-generated plan for approve-only confirmation by IT
3. On approval:
   - Post a welcome message to the specified Slack channel
   - Create a Jira onboarding task in the specified project
4. Write a report with API results as artifact

## Required Connections

- **AI API Key** — Claude API key for content generation (Anthropic)
- **Slack** — OAuth token for posting messages to Slack channels
- **Jira** — OAuth token for creating issues in Jira Cloud

## Expected Context Variables

- `new_hire_name` — New employee's full name
- `new_hire_email` — New employee's email address
- `company_name` — Organization name
- `manager_email` — Direct manager's email address
- `start_date` — Employee's start date
- `slack_channel` — Slack channel for the welcome message (e.g. general)
- `jira_project` — Jira project key for the onboarding task (e.g. HR)

## Output

Writes `account-provisioning.md` to Firebase Storage containing the
provisioning plan, approval status, and API integration results.
