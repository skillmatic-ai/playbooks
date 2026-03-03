---
name: "Web Prototype Generator"
id: web-prototype-generator
description: "Generate a functional web prototype from a PRD or feature specification"
version: "1.0"
category: "design"
compatible_apis: [bolt]
author: "skillmatic"
---

# Web Prototype Generator Skill

## Instructions

You are generating a functional web prototype based on a Product Requirements Document (PRD) or feature specification from prior step reports.

### Process

1. **Extract requirements**: Read the PRD from prior step context and identify:
   - Top 2-3 user stories or JTBD themes to prototype
   - Key user flows and interactions
   - Required UI components and data displays
2. **Define prototype scope**: Focus on the most critical user journeys
   - Prioritize flows that validate the core value proposition
   - Include realistic sample data, not lorem ipsum
   - Keep interactions authentic (buttons, forms, navigation)
3. **Generate the prototype**:
   - Create a single-page or multi-page interactive web prototype
   - Use modern UI patterns (cards, modals, sidebars, etc.)
   - Include responsive layout considerations
   - Add realistic copy derived from the PRD's problem statement
4. **Present for review**: Show the prototype to the Designer for UX feedback
   - Highlight which user stories are covered
   - Call out any UX assumptions made
   - Ask for specific feedback on flow, layout, and interactions

### Design Principles

- **Clarity over polish**: Focus on making the user flow understandable
- **Real data**: Use sample data that reflects actual use cases from the research
- **Interactive**: Buttons and navigation should work, not just be visual
- **Accessible**: Use sufficient contrast, readable font sizes, semantic structure

### Output Format

Provide:
1. **Prototype URL**: Link to the hosted prototype
2. **Scope Summary**: Which user stories / JTBD themes are covered
3. **Key Screens**: List of screens with brief descriptions
4. **UX Assumptions**: Design decisions made without explicit guidance
5. **Feedback Requests**: Specific questions for the reviewer
