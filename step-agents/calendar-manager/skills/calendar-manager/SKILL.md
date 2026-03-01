---
name: calendar-manager
description: AI-powered week-1 meeting schedule generation with Google Calendar event creation. Uses Claude for schedule optimization and Google Calendar API for real events. Non-interactive, exception-only approval.
---

# Calendar Manager Skill

Uses Claude API to generate an optimized first-week meeting schedule, then
creates real Google Calendar events via the Calendar API v3. The Gmail OAuth
token includes the calendar.events scope. Non-interactive with exception-only
approval.

## Behavior

1. Read onboarding context (new hire name, start date, manager)
2. LLM generates a structured JSON schedule (12-15 meetings)
3. Create real Google Calendar events via the Calendar API
4. LLM generates a human-readable schedule report with calendar links
5. Upload the report as artifact

## Required Connections

- **AI API Key** — Claude API key for content generation (Anthropic)
- **Gmail** — OAuth token with `calendar.events` scope for creating events

## Expected Context Variables

- `new_hire_name` — New employee's full name
- `new_hire_email` — New employee's email address
- `start_date` — Employee's start date
- `manager_email` — Direct manager's email address
- `company_name` — Organization name

## Output

Writes `meeting-schedule.md` to Firebase Storage containing the AI-generated
week-1 meeting schedule with Google Calendar integration results.
