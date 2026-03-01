---
name: email-drafter
description: AI-powered welcome email drafting with Gmail delivery. Uses Claude to generate personalized emails and sends them via Gmail API. Supports review-and-edit approval with 3-phase checkpoint/resume.
---

# Email Drafter Skill

Uses Claude API to generate personalized welcome emails for new hires, then
delivers them via the Gmail API. Supports a 3-phase HITL workflow: contextual
question, AI draft generation with review-and-edit approval, and Gmail delivery.

## Behavior

1. LLM generates a contextual question about special topics to include
2. LLM drafts a personalized welcome email from context + user's answer
3. Submit the AI-generated draft for review-and-edit approval
4. On approval: send the email via Gmail API to the new hire

## Required Connections

- **AI API Key** — Claude API key for content generation (Anthropic)
- **Gmail** — OAuth token for sending emails via Gmail API

## Expected Context Variables

- `new_hire_name` — New employee's full name
- `new_hire_email` — New employee's email address
- `company_name` — Organization name
- `manager_email` — Direct manager's email address
- `start_date` — Employee's start date

## Output

Writes `welcome-email.md` to Firebase Storage containing the finalized
welcome email. If Gmail delivery succeeds, includes the message ID.
