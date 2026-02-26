# Contributing to Skillmatic Playbooks

## Submitting a Playbook

### 1. Create a Directory

Create a new directory under `playbooks/community/` with a descriptive kebab-case name:

```
playbooks/community/my-playbook-name/
  PLAYBOOK.md
```

### 2. Write PLAYBOOK.md

Your `PLAYBOOK.md` must be in **v2 format** with YAML frontmatter between `---` delimiters.

**Required frontmatter fields:**

| Field | Type | Description |
|---|---|---|
| `name` | string | Human-readable playbook name |
| `version` | string | Semver version (e.g., `1.0.0`) |
| `description` | string | What the playbook does |
| `category` | string | Category (e.g., HR, Operations, Engineering, Security) |
| `schemaVersion` | string | Must be `v2` |
| `trigger` | object | How the playbook is initiated |
| `steps` | array | Step definitions (see below) |

**Required step fields:**

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique step identifier (kebab-case) |
| `order` | number | Execution order |
| `title` | string | Human-readable step title |
| `assignedRole` | string | Role responsible for this step |
| `agentImage` | string | Docker image reference for the step agent |
| `approval` | string | `approve_only`, `review_and_edit`, or `exception_only` |

**Optional step fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `timeoutMinutes` | number | 30 | Max execution time |
| `interactive` | boolean | false | Whether step may pause for user input |
| `dependencies` | string[] | [] | Step IDs this step depends on |
| `description` | string | — | Step description |

**Optional frontmatter fields:**

| Field | Type | Description |
|---|---|---|
| `variables` | array | Template variables for personalization |
| `participants` | array | Roles involved in the playbook |
| `metadata` | object | Author, tags, etc. |

### 3. Write Markdown Body

The markdown body after the frontmatter closing `---` provides detailed instructions for each step. Use `## Step: {step-id}` headers to associate guidance with specific steps.

```markdown
## Step: my-step-id

### Agent guidance

Detailed instructions for the agent...

### Instructions for reviewer

What the human reviewer should check...
```

### 4. Submit a PR

1. Fork this repository
2. Create a branch
3. Add your playbook directory
4. Submit a pull request

The CI pipeline will validate your PLAYBOOK.md format and check that all referenced `agentImage` values exist in the Artifact Registry.

## Submitting a Step Agent

### 1. Create a Directory

```
step-agents/my-agent-name/
  Dockerfile
  requirements.txt
  entrypoint.py
  skills/
    my-skill/
      SKILL.md
```

### 2. Write SKILL.md

Follow the [Agent Skills](https://agentskills.io) standard. Required frontmatter:

```yaml
---
name: my-skill
description: What this skill does
---
```

### 3. Create Dockerfile

Your Dockerfile must:
- Use `python:3.12-slim` as the base image
- Install dependencies from `requirements.txt`
- Copy the entrypoint and skills
- Run as a non-root user
- Use `ENTRYPOINT ["python", "entrypoint.py"]`

### 4. Submit a PR

The CI pipeline will:
1. Verify a `SKILL.md` exists in `skills/*/`
2. Build the Docker image
3. Push to Artifact Registry on merge
