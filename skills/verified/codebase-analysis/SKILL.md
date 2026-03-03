---
name: "Codebase Analysis"
id: codebase-analysis
description: "Analyze repository structure, tech stack, and code patterns to inform implementation planning"
version: "1.0"
category: "engineering"
compatible_apis: [github, gitlab]
author: "skillmatic"
---

# Codebase Analysis Skill

## Instructions

You are performing a structural analysis of a codebase to understand its architecture, patterns, and complexity before estimating implementation effort.

### Process

1. **Repository overview**: Get repo metadata (language, size, activity)
2. **Directory structure mapping**: Explore the top-level and key subdirectories
   - Identify framework and build system (package.json, requirements.txt, go.mod, etc.)
   - Map the module/package structure
   - Locate tests, configs, CI/CD, and documentation
3. **Architectural patterns**: Read key files to identify:
   - Application architecture (monolith, microservices, modular monolith)
   - State management approach
   - API layer design (REST, GraphQL, gRPC)
   - Database and ORM patterns
   - Authentication and authorization model
4. **Code search for feature context**: Search for modules related to the proposed feature
   - Find existing implementations of similar functionality
   - Identify shared utilities and abstractions that can be reused
   - Locate integration points where new code would connect
5. **Dependency analysis**: Review dependency files for:
   - Major framework versions and compatibility
   - Third-party services and SDKs already integrated
   - Potential library candidates for the proposed feature
6. **Recent activity**: Review recent PRs and commits for:
   - Active development areas (avoid conflicts)
   - Code style and conventions
   - Review process and testing expectations

### Output Format

Provide a markdown report with:
1. **Tech Stack Summary**: Languages, frameworks, major dependencies
2. **Architecture Overview**: High-level module map and data flow
3. **Relevant Modules**: Files and directories related to the proposed feature
4. **Reusable Patterns**: Existing abstractions, utilities, or patterns to leverage
5. **Integration Points**: Where new code would connect to existing systems
6. **Code Conventions**: Style, testing patterns, and PR expectations observed
7. **Complexity Indicators**: LOC, module count, dependency depth in affected areas
