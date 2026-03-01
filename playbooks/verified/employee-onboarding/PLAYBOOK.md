---
id: "employee-onboarding"
name: "Employee Onboarding"
version: "1.0.0"
description: "End-to-end employee onboarding workflow: welcome email drafting, account provisioning, meeting scheduling, and summary report. Exercises parallel steps, HITL approvals, DAG dependencies, and file generation."
category: "HR"
schemaVersion: "v2"

trigger:
  type: human_initiation
  role: HR
  inputs:
    - name: new_hire_name
      type: text
      label: "New Hire Name"
      placeholder: "e.g. Jane Smith"
      required: true
    - name: new_hire_email
      type: email
      label: "New Hire Email"
      placeholder: "e.g. jane@company.com"
      required: true
    - name: manager_email
      type: email
      label: "Manager Email"
      placeholder: "e.g. mgr@company.com"
      required: true
    - name: start_date
      type: date
      label: "Start Date"
      required: true
    - name: slack_channel
      type: slack:channel
      label: "Slack Channel"
      placeholder: "Select a Slack channel..."
      required: true
    - name: jira_project
      type: jira:project
      label: "Jira Project"
      placeholder: "Select a Jira project..."
      required: true

participants:
  - role: HR
    minCount: 1
  - role: IT
    minCount: 1

required_connections:
  - ai_api_key
  - gmail
  - slack
  - jira

variables:
  - name: company_name
    source: "org.name"
    required: true
    description: "Organization name from org settings"
  - name: new_hire_name
    source: "run.context.new_hire_name"
    required: true
    description: "New employee's full name"
  - name: new_hire_email
    source: "run.context.new_hire_email"
    required: true
    description: "New employee's email address"
  - name: manager_email
    source: "run.context.manager_email"
    required: true
    description: "Direct manager's email address"
  - name: start_date
    source: "run.context.start_date"
    required: true
    description: "Employee's start date (e.g. 2025-03-15)"
  - name: slack_channel
    source: "run.context.slack_channel"
    required: true
    description: "Slack channel for the welcome message (e.g. general, new-hires)"
  - name: jira_project
    source: "run.context.jira_project"
    required: true
    description: "Jira project key for the onboarding task (e.g. HR, ON)"

steps:
  - id: welcome-email
    order: 1
    title: "Draft Welcome Email"
    assignedRole: HR
    agentImage: email-drafter
    timeoutMinutes: 15
    interactive: true
    approval: review_and_edit
    dependencies: []

  - id: account-setup
    order: 2
    title: "Provision Accounts"
    assignedRole: IT
    agentImage: account-provisioner
    timeoutMinutes: 30
    interactive: true
    approval: approve_only
    dependencies: []

  - id: schedule-meetings
    order: 3
    title: "Schedule Onboarding Meetings"
    assignedRole: HR
    agentImage: calendar-manager
    timeoutMinutes: 10
    interactive: false
    approval: exception_only
    dependencies: [welcome-email, account-setup]

  - id: onboarding-summary
    order: 4
    title: "Generate Onboarding Report"
    assignedRole: HR
    agentImage: report-generator
    timeoutMinutes: 10
    interactive: false
    approval: exception_only
    dependencies: [schedule-meetings]
---

# Employee Onboarding Playbook

This playbook automates the end-to-end onboarding process for a new employee
using AI-powered content generation and real API integrations. It runs four
steps: two in parallel (welcome email drafting with Gmail delivery and account
provisioning with Slack/Jira integration), followed by AI-generated meeting
scheduling, and concludes with an AI-compiled executive summary report.

## Step: welcome-email

Draft a personalized welcome email for {{new_hire_name}} joining
{{company_name}} on {{start_date}}. The email should be addressed to
{{new_hire_email}} and CC {{manager_email}}.

The agent will:
1. Use Claude to generate a contextual question about special topics to include
2. Use Claude to draft a personalized welcome email incorporating the answer
3. Submit the AI-generated draft for review-and-edit approval by the HR participant
4. On approval, send the email via Gmail API to {{new_hire_email}}

The HR reviewer can approve the draft as-is, edit it, or reject it entirely.

### Reviewer Instructions

Review the generated welcome email for:
- Correct recipient and CC addresses
- Professional tone appropriate for {{company_name}}
- Accurate start date and first-week schedule overview
- Any company-specific information that should be added or removed

## Step: account-setup

Provision standard accounts and access for {{new_hire_name}}
({{new_hire_email}}). Generate the list of accounts to create based on
company standards.

The agent will:
1. Use Claude to generate a tailored account provisioning plan
2. Submit the AI-generated plan for approve-only confirmation by IT
3. On approval, post a welcome message to Slack #{{slack_channel}}
4. Create a Jira onboarding task in the {{jira_project}} project

IT must approve before API actions are executed.

### Reviewer Instructions

Verify that:
- The correct email address is used across all services
- Access levels are appropriate for the new hire's role
- No unnecessary or restricted services are included

## Step: schedule-meetings

Schedule the standard onboarding meetings for {{new_hire_name}} starting
{{start_date}}. This step runs automatically after both the welcome email
and account setup are complete.

The agent will:
1. Use Claude to generate an optimized week-1 meeting schedule as structured JSON
2. Create real Google Calendar events via the Calendar API (12-15 meetings)
3. Generate a human-readable schedule report with calendar links
4. Upload the report as an artifact

This step is non-interactive and executes automatically (exception_only
approval).

## Step: onboarding-summary

Compile a comprehensive onboarding report for {{new_hire_name}} summarizing
all completed steps: the welcome email status, provisioned accounts, and
scheduled meetings.

The agent will:
1. Read results from all previous steps via Firestore
2. Use Claude to compile a narrative executive report with analysis
3. Upload the AI-generated report as a downloadable artifact

This step is non-interactive and executes automatically (exception_only
approval).
