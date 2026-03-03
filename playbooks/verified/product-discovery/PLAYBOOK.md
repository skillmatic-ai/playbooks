---
id: product-discovery
name: "Intent-Driven Product Discovery"
version: "1.0.0"
description: "End-to-end product discovery workflow: analyze support tickets for pain points, draft a living PRD, generate an interactive prototype, and assess technical feasibility."
schemaVersion: v3
category: "product-management"
tags: [product, research, validation, prototype, discovery]
author: "skillmatic"
trigger:
  type: human_initiation
  role: Product
  inputs:
    - name: product_area
      type: text
      label: "Product Area"
      placeholder: "e.g., Onboarding, Billing, Search"
      required: true
    - name: lookback_days
      type: text
      label: "Lookback Period (days)"
      placeholder: "90"
      required: false
participants:
  - role: Product
    description: "Product Manager — owns the PRD and reviews all outputs"
  - role: Engineering
    description: "Tech Lead — reviews feasibility and estimates effort"
  - role: Design
    description: "Designer — reviews prototype and provides UX feedback"
variables:
  - name: product_area
    source: run.triggerInputs.product_area
    required: true
  - name: lookback_days
    source: run.triggerInputs.lookback_days
    required: false
    description: "Number of days to look back for ticket analysis (default: 90)"
steps:
  - id: sentiment-synthesis
    order: 1
    title: "Sentiment Synthesis"
    description: "Analyze recent support tickets to identify JTBD themes and pain intensity."
    assignedRole: Product
    api: zendesk
    skills:
      - jtbd-clustering
      - sentiment-analysis
    approval: review_and_edit
    interactive: true
    timeoutMinutes: 60
  - id: living-spec
    order: 2
    title: "Draft Living Spec"
    description: "Create a PRD in Notion based on the sentiment synthesis findings."
    assignedRole: Product
    api: notion
    skills:
      - prd-template-v2
    approval: review_and_edit
    interactive: true
    dependencies:
      - sentiment-synthesis
    timeoutMinutes: 60
  - id: prototype
    order: 3
    title: "Generate Prototype"
    description: "Create a functional web prototype based on the PRD."
    assignedRole: Design
    api: bolt
    skills:
      - web-prototype-generator
    approval: review_and_edit
    interactive: true
    dependencies:
      - living-spec
    timeoutMinutes: 120
  - id: feasibility
    order: 4
    title: "Feasibility Analysis"
    description: "Analyze the codebase and estimate implementation effort for the proposed features."
    assignedRole: Engineering
    api: github
    inputs:
      - name: target_repo
        type: github:repository
        label: "Select GitHub Repository"
        required: true
    skills:
      - feasibility-report
      - codebase-analysis
    approval: approve_only
    interactive: true
    dependencies:
      - living-spec
      - prototype
    timeoutMinutes: 90
---

# Intent-Driven Product Discovery

A four-step workflow that transforms raw support ticket data into a validated product specification with a working prototype and feasibility analysis — all within 48 hours.

## Overview

This playbook orchestrates three team roles (Product, Design, Engineering) across four API services (Zendesk, Notion, Bolt, GitHub) to take a product area from raw user pain signals to a validated, scoped spec.

**Flow:**
1. PM analyzes support tickets to find JTBD clusters and pain scores
2. PM drafts a PRD in Notion using those findings as evidence
3. Designer generates an interactive prototype from the PRD
4. Engineer assesses technical feasibility against the actual codebase

Each step receives the prior step's report as context, creating a natural chain of evidence.

## Step: sentiment-synthesis

### Agent guidance

Analyze support tickets from the last {{lookback_days}} days (default: 90) related to the "{{product_area}}" product area.

**Phase 1 — Data collection:**
1. Search tickets using query: `tags:{{product_area}} created>{{lookback_days}}d`
2. If few results, broaden to: `"{{product_area}}" created>{{lookback_days}}d`
3. Export up to 200 tickets for analysis

**Phase 2 — JTBD clustering:**
1. Read each ticket's subject and description
2. Identify the underlying job: "When [situation], I want to [motivation], so I can [outcome]"
3. Group into 5-8 clusters ranked by frequency
4. Score pain intensity (1-5) for each cluster

**Phase 3 — Sentiment analysis:**
1. Classify each ticket: positive, neutral, negative, critical
2. Flag churn-risk tickets (pain score 4-5, language like "cancel", "switch to", "looking at alternatives")
3. Aggregate sentiment distribution and trends

**Phase 4 — Review:**
1. Present the full analysis to the Product Manager
2. Show the cluster table with names, counts, pain scores, and representative quotes
3. Ask the PM to confirm or rename clusters before finalizing
4. Incorporate feedback and finalize the report

## Step: living-spec

### Agent guidance

Using the sentiment synthesis report from the previous step, draft a comprehensive PRD in the Product Manager's Notion workspace.

**Phase 1 — Preparation:**
1. Read the sentiment synthesis report thoroughly
2. Identify the top 3-5 JTBD clusters by combined pain score and frequency
3. Note the churn-risk signals and key quotes

**Phase 2 — PRD creation:**
1. Search for an existing PRD database in the workspace (query: "PRD" or "Product Requirements")
2. If found, create a new page in that database; otherwise create a standalone page
3. Title: "PRD: {{product_area}} — [Primary Job Theme]"
4. Follow the PRD Template v2 structure:
   - Problem Statement (backed by ticket data)
   - User Stories / JTBD (from clusters)
   - Proposed Solution (high-level approach)
   - Success Metrics (derived from pain scores)
   - Technical Considerations (preliminary)
   - Timeline & Milestones (placeholder)
   - Open Questions

**Phase 3 — Review:**
1. Present the draft PRD to the Product Manager
2. Highlight areas that need stakeholder input (open questions)
3. Ask for specific feedback on scope and prioritization
4. Update the Notion page with feedback

**Phase 4 — Finalize:**
1. After PM approval, note the Notion page URL as an artifact
2. Summarize key decisions in the step report

## Step: prototype

### Agent guidance

Based on the PRD from the previous step, generate a functional web prototype.

**Phase 1 — Requirements extraction:**
1. Read the PRD report from the living-spec step
2. Identify the top 2-3 user stories to prototype
3. Define the key screens and user flows

**Phase 2 — Prototype generation:**
1. Generate an interactive prototype covering the primary user journey
2. Use realistic sample data derived from the PRD's problem statement
3. Include navigation between key screens
4. Ensure buttons, forms, and interactions are functional

**Phase 3 — Review:**
1. Present the prototype to the Designer
2. Provide the prototype URL and list of screens covered
3. Ask for feedback on:
   - Information hierarchy and layout
   - Interaction patterns and flow
   - Missing screens or edge cases
4. Iterate based on feedback

**Phase 4 — Finalize:**
1. After Designer approval, record the prototype URL as an artifact
2. Document which user stories are covered vs. deferred

## Step: feasibility

### Agent guidance

Analyze the team's codebase to estimate implementation effort for the features defined in the PRD and prototype.

**Phase 1 — Context gathering:**
1. Read the PRD report (from living-spec) and prototype report (from prototype step)
2. Extract the key features and technical requirements
3. Parse the target repository: {{target_repo}}

**Phase 2 — Codebase analysis:**
1. Get repository overview (languages, size, recent activity)
2. Map the directory structure and identify the architecture
3. Search for modules related to each proposed feature
4. Identify reusable patterns, utilities, and integration points

**Phase 3 — Feasibility assessment:**
1. For each feature from the PRD:
   - Estimate complexity (Simple / Medium / Complex / Very Complex)
   - List files that would need modification
   - Identify risks and dependencies
   - Estimate effort in person-weeks
2. Provide an overall Go/No-Go recommendation with confidence level

**Phase 4 — Review:**
1. Present the feasibility report to the Tech Lead
2. Highlight any blockers or high-risk areas
3. Wait for approval before finalizing
