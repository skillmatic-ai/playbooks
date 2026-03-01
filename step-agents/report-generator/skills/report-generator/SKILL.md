---
name: report-generator
description: AI-powered executive onboarding report compilation. Uses Claude to analyze step results and generate a narrative report. Non-interactive, auto-executes with exception-only approval.
---

# Report Generator Skill

Uses Claude API to compile a comprehensive executive onboarding report from
all prior step results. Reads step data and file metadata from Firestore
(cross-step data access) and generates a narrative analysis.

## Behavior

1. Read onboarding context variables
2. Query all step documents from Firestore for result summaries
3. Query all file documents from Firestore for artifact metadata
4. LLM compiles a narrative report with executive summary, step analysis,
   artifacts table, action items, and IT checklist
5. Upload the report as a downloadable artifact to Firebase Storage

## Required Connections

- **AI API Key** — Claude API key for content generation (Anthropic)

## Expected Context Variables

- `new_hire_name` — New employee's full name
- `new_hire_email` — New employee's email address
- `company_name` — Organization name
- `manager_email` — Direct manager's email address
- `start_date` — Employee's start date

## Output

Writes `onboarding-report.md` to Firebase Storage containing the AI-generated
comprehensive onboarding summary report.
