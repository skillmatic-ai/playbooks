---
name: "Sentiment Analysis"
id: sentiment-analysis
description: "Analyze pain intensity and sentiment from customer communications"
version: "1.0"
category: "product-management"
compatible_apis: [zendesk, notion]
author: "skillmatic"
---

# Sentiment Analysis Skill

## Instructions

You are performing sentiment and pain-intensity analysis on customer support tickets or user feedback.

### Process

1. **Classify sentiment** for each item: positive, neutral, negative, critical
2. **Score pain intensity** (1-5 scale):
   - 1: Minor inconvenience, workaround exists
   - 2: Moderate frustration, impacts workflow
   - 3: Significant pain, frequent occurrence
   - 4: Severe issue, considering alternatives
   - 5: Critical blocker, active churn signal
3. **Identify churn signals**: Language indicating the user may leave ("looking at alternatives", "cancel", "switch to")
4. **Extract emotion markers**: Specific phrases indicating frustration level
5. **Aggregate by time period**: Show sentiment trends if dates are available

### Output Format

Provide a markdown report with:
1. Overall sentiment distribution (pie chart description)
2. Average pain score with trend
3. Top churn-risk tickets (pain score 4-5)
4. Sentiment trend over time (if applicable)
5. Key emotion markers and their frequency
