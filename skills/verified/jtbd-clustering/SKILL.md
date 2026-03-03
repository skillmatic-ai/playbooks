---
name: "JTBD Clustering"
id: jtbd-clustering
description: "Cluster support tickets and user feedback into Jobs-to-be-Done themes"
version: "1.0"
category: "product-management"
compatible_apis: [zendesk, notion]
author: "skillmatic"
---

# JTBD Clustering Skill

## Instructions

You are analyzing customer support tickets and user feedback to identify Jobs-to-be-Done (JTBD) themes.

### Process

1. **Read all tickets/feedback** provided as input data
2. **Extract user intent** from each ticket — what is the user trying to accomplish?
3. **Cluster by job** — Group tickets by the underlying job, not by surface-level topic
4. **Name each cluster** using the JTBD format: "When [situation], I want to [motivation], so I can [outcome]"
5. **Rank clusters** by frequency and pain intensity
6. **Output a structured summary** with cluster names, ticket counts, representative quotes, and pain scores

### JTBD Format

Each cluster should follow the format:
- **Job Statement**: "When [situation], I want to [motivation], so I can [outcome]"
- **Ticket Count**: Number of tickets in this cluster
- **Pain Score**: 1-5 (derived from language intensity, frequency, and churn signals)
- **Representative Quotes**: 2-3 actual quotes from tickets
- **Related Keywords**: Common terms in this cluster

### Output Format

Provide a markdown report with:
1. Executive summary (top 3 jobs)
2. Full cluster table
3. Methodology notes
