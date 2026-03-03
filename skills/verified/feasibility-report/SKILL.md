---
name: "Feasibility Report"
id: feasibility-report
description: "Analyze codebase and estimate implementation effort for a proposed feature"
version: "1.0"
category: "engineering"
compatible_apis: [github, gitlab]
author: "skillmatic"
---

# Feasibility Report Skill

## Instructions

You are performing a technical feasibility analysis for a proposed product feature, based on the codebase and PRD provided.

### Process

1. **Understand the requirement**: Read the PRD or feature description from prior step reports
2. **Explore the codebase**: Search for relevant files, modules, and patterns
3. **Identify touch points**: List all files/modules that would need modification
4. **Assess complexity**:
   - Simple (< 1 week): Config changes, UI tweaks, well-isolated additions
   - Medium (1-3 weeks): New module, cross-cutting changes, API additions
   - Complex (3-6 weeks): Architecture changes, new infrastructure, migration needed
   - Very Complex (6+ weeks): Fundamental redesign, new system integration
5. **Flag risks**: Dependencies, breaking changes, performance concerns
6. **Estimate effort**: T-shirt size with confidence level

### Output Format

Provide a markdown report with:
1. **Feasibility Summary**: Go/No-Go recommendation with confidence (high/medium/low)
2. **Complexity Assessment**: T-shirt size + justification
3. **Architecture Impact**: What changes and what stays the same
4. **File Touch Map**: List of files to modify with brief description of changes
5. **Risks & Mitigations**: Table of risks with severity and mitigation strategy
6. **Effort Estimate**: Person-weeks with breakdown by component
7. **Recommendations**: Suggested approach, phasing, or alternatives
