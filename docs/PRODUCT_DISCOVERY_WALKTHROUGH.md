# Product Discovery Playbook — Demo Walkthrough

This document walks through the Intent-Driven Product Discovery playbook end-to-end, showing what each team member experiences and what appears in the chat thread at each stage.

## Prerequisites

### Team Roles

| Role | Member | Required OAuth |
|------|--------|----------------|
| Product (PM) | Product Manager | Zendesk, Notion |
| Design | Product Designer | Bolt |
| Engineering | Tech Lead | GitHub |

### Before Launch

1. All participants must be org members with their roles assigned
2. Each member connects their OAuth accounts via Settings → Connections:
   - PM: Connect Zendesk (read access to tickets) and Notion (read/write pages)
   - Designer: Connect Bolt (prototype creation)
   - Tech Lead: Connect GitHub (read access to target repository)
3. If a member hasn't connected, the playbook will pause at that step with an OAuth prompt card

---

## Launch

**Who:** Product Manager (or any member)

1. Open Skillmatic → Runs → click "New Run"
2. Select "Intent-Driven Product Discovery" from the catalog
3. Fill in trigger inputs:
   - **Product Area**: e.g., "Onboarding"
   - **Lookback Period**: e.g., "90" (days)
4. Click "Launch"

> **Note:** The GitHub repository is no longer requested at launch — it will be asked just-in-time to the Tech Lead before the Feasibility step starts (see Step 4).

**Chat thread shows:**
```
──── Playbook Started ────
Intent-Driven Product Discovery v1.0.0
Investigating: Onboarding (90-day lookback)
```

---

## Step 1: Sentiment Synthesis (Zendesk → PM)

**API Agent:** Zendesk
**Assigned to:** Product Manager
**Skills:** jtbd-clustering, sentiment-analysis

### What Happens

1. **OAuth check** — If PM hasn't connected Zendesk, a card appears:
   ```
   🔑 Zendesk access required
   [Product Manager] needs to connect Zendesk to proceed.
   [Connect Zendesk →]
   ```

2. **Agent starts** — Chat shows step transition:
   ```
   ── Step 1 of 4: Sentiment Synthesis ──
   Analyzing support tickets...
   ```

3. **Agent works** — The Zendesk agent:
   - Searches tickets tagged with "Onboarding" from the last 90 days
   - Exports up to 200 tickets
   - Clusters them into JTBD themes
   - Scores pain intensity per cluster

4. **Review pause** — Agent presents findings for PM review:
   ```
   [Agent] I found 147 tickets and identified 6 JTBD clusters:

   | Cluster | Count | Pain | Job Statement |
   |---------|-------|------|---------------|
   | Quick Start | 42 | 4.2 | When starting a new account... |
   | Team Setup | 31 | 3.8 | When inviting team members... |
   | ...     | ...   | ...  | ...           |

   Do the cluster names and groupings look right?
   Would you like to rename or merge any clusters?

   [Text input field]
   [Submit]
   ```

5. **PM responds** — PM types feedback, shown as right-aligned bubble:
   ```
   [PM] Merge "Quick Start" and "First Login" into one cluster
   called "Getting Started". The rest look good.
   ```

6. **Step completes** — Agent finalizes report:
   ```
   ── ✓ Sentiment Synthesis Complete ──
   Report: 6 JTBD clusters, avg pain 3.4, 12 churn-risk tickets
   [View Full Report ▾]
   ```

---

## Step 2: Draft Living Spec (Notion → PM)

**API Agent:** Notion
**Assigned to:** Product Manager
**Skills:** prd-template-v2
**Receives:** Step 1 report as context

### What Happens

1. **Agent starts** — Receives the sentiment synthesis report automatically:
   ```
   ── Step 2 of 4: Draft Living Spec ──
   Creating PRD in Notion...
   ```

2. **Agent works** — The Notion agent:
   - Reads the sentiment report from Step 1
   - Searches for existing PRD database in Notion workspace
   - Creates a new page: "PRD: Onboarding — Getting Started"
   - Fills in all sections using JTBD clusters as evidence

3. **Review pause** — Agent presents draft for PM and Tech Lead review:
   ```
   [Agent] I've created a PRD in your Notion workspace:

   📄 PRD: Onboarding — Getting Started
   Sections: Problem Statement, User Stories, Proposed Solution,
   Success Metrics, Technical Considerations, Timeline, Open Questions

   Key decisions for your review:
   - Prioritized "Getting Started" (pain 4.2) as primary focus
   - Proposed self-service onboarding wizard as solution
   - Success metric: reduce support tickets by 40%

   Please review and let me know if you'd like changes.

   [Text input field]
   [Submit]
   ```

4. **PM provides feedback** → Agent updates Notion page

5. **Step completes** with artifact card:
   ```
   ── ✓ Draft Living Spec Complete ──
   Report: PRD created with 7 sections, 5 user stories

   ┌──────────────────────────────────────┐
   │ 📄 PRD: Onboarding — Getting Started │
   │ Notion page                          │
   │ [Open in Notion →]                   │
   └──────────────────────────────────────┘
   ```

---

## Step 3: Generate Prototype (Bolt → Designer)

**API Agent:** Bolt
**Assigned to:** Designer
**Skills:** web-prototype-generator
**Receives:** Step 2 report as context

### What Happens

1. **OAuth check** — If Designer hasn't connected Bolt:
   ```
   🔑 Bolt access required
   [Designer] needs to connect Bolt to proceed.
   [Connect Bolt →]
   ```

2. **Agent works** — Reads the PRD report, generates interactive prototype focusing on top 2-3 user stories

3. **Review pause** — Designer reviews:
   ```
   [Agent] I've generated a prototype covering these flows:
   1. New user onboarding wizard (3 screens)
   2. Team invitation flow (2 screens)
   3. First project setup (2 screens)

   UX assumptions:
   - Used stepper pattern for multi-step wizard
   - Added progress indicator
   - Skip option for optional steps

   Questions for review:
   - Should the wizard be dismissible?
   - Preferred color scheme for CTAs?

   [Text input field]
   [Submit]
   ```

4. **Designer responds** with UX feedback → Agent iterates

5. **Step completes** with artifact card:
   ```
   ── ✓ Generate Prototype Complete ──

   ┌──────────────────────────────────────┐
   │ ⚡ Onboarding Wizard Prototype       │
   │ Interactive prototype                │
   │ [Open in Bolt →]                     │
   └──────────────────────────────────────┘
   ```

---

## Step 4: Feasibility Analysis (GitHub → Tech Lead)

**API Agent:** GitHub
**Assigned to:** Engineering (Tech Lead)
**Skills:** feasibility-report, codebase-analysis
**Receives:** Steps 2 + 3 reports as context

### What Happens

1. **Step input request** — Before the agent can start, the Tech Lead must select the target repository. A configuration card appears in the chat thread:
   ```
   ┌──────────────────────────────────────────────────┐
   │ ⚙ Step Configuration               2m ago       │
   │ ──────────────────────────────────────────────── │
   │ [Engineering]  Feasibility Analysis              │
   │                                                  │
   │ Select GitHub Repository                         │
   │ ┌──────────────────────────────────────┐         │
   │ │ Search repositories...         ▾    │         │
   │ └──────────────────────────────────────┘         │
   │                                                  │
   │                            [Submit →]            │
   └──────────────────────────────────────────────────┘
   ```
   The dropdown is populated from the Tech Lead's connected GitHub account.

2. **Agent works** — After the Tech Lead submits, the GitHub agent:
   - Reads PRD and prototype reports from prior steps
   - Analyzes the selected repo (e.g., `acme-corp/web-app`)
   - Maps directory structure, identifies tech stack
   - Searches for modules related to onboarding
   - Estimates complexity per feature

3. **Approval pause** — Tech Lead reviews:
   ```
   [Agent] Feasibility analysis for acme-corp/web-app:

   **Tech Stack:** React 18, Node.js, PostgreSQL
   **Relevant modules:** src/auth/, src/onboarding/ (exists but minimal)

   | Feature | Complexity | Effort | Risk |
   |---------|-----------|--------|------|
   | Wizard component | Medium | 1.5 wk | Low |
   | Team invite flow | Medium | 1 wk | Medium (email service) |
   | Progress tracking | Simple | 0.5 wk | Low |

   **Recommendation:** GO — 3-4 weeks total, Medium confidence
   **Key risk:** Email service integration for team invites

   [Approve] [Reject] [Request Changes]
   ```

4. **Tech Lead approves** → shown as right-aligned bubble:
   ```
   [Tech Lead] ✓ Approved
   ```

5. **Step completes**:
   ```
   ── ✓ Feasibility Analysis Complete ──
   Report: GO recommendation, 3-4 weeks, Medium confidence
   [View Full Report ▾]
   ```

---

## Playbook Complete

```
──── Playbook Completed ────
Intent-Driven Product Discovery finished successfully.
4 of 4 steps completed.
Duration: 2h 15m

Artifacts:
📄 PRD: Onboarding — Getting Started  [Open in Notion →]
⚡ Onboarding Wizard Prototype         [Open in Bolt →]
```

### Deliverables

| Step | Output | Location |
|------|--------|----------|
| Sentiment Synthesis | JTBD clusters + pain scores | Step report (in-app) |
| Living Spec | Full PRD | Notion page |
| Prototype | Interactive prototype | Bolt URL |
| Feasibility | Go/No-Go + effort estimate | Step report (in-app) |

---

## Multi-User Experience

All org members can observe the playbook in real-time:

- **Active Runs tab** shows the run with live status
- **Chat thread** updates in real-time via Firestore onSnapshot
- When a step needs **your** role's input, you see the input form
- When a step needs **another** role's input, you see "Waiting for [Role]..."
- **Artifact cards** are visible to everyone with "Open in [Service]" links

---

## Troubleshooting

| Issue | Resolution |
|-------|-----------|
| OAuth card won't go away | Reconnect the service in Settings → Connections |
| Step stuck on "running" | Check step timeout (60-120 min); use Abort if needed |
| Agent gives incorrect results | Use the review pause to provide corrections |
| Step failed | Check the error message; re-launch the playbook if needed |
| Missing artifact card | Verify the agent created the external resource successfully |
