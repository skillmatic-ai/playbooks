"""Playbook Parser — parses PLAYBOOK.md YAML frontmatter and markdown body.

Extracts variables, steps, metadata, and per-step markdown sections into
a structured PlaybookDefinition for hydration and orchestration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class VariableDef:
    name: str
    source: str
    required: bool = True
    description: str = ""


@dataclass
class StepDef:
    id: str
    order: int
    title: str
    assigned_role: str
    agent_image: str = ""
    timeout_minutes: int = 30
    interactive: bool = False
    approval: str = "approve_only"
    dependencies: list[str] = field(default_factory=list)
    description: str = ""
    instruction: str = ""
    required_connections: list[str] = field(default_factory=list)


@dataclass
class PlaybookDefinition:
    name: str
    version: str
    description: str
    category: str
    schema_version: str
    trigger: dict
    participants: list[dict]
    variables: list[VariableDef]
    steps: list[StepDef]
    markdown_body: str
    step_sections: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Matches "## Step: step-id" headings (case-insensitive, flexible whitespace)
_STEP_HEADING_RE = re.compile(
    r"^##\s+Step:\s*(\S+)\s*$", re.MULTILINE | re.IGNORECASE
)


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Split YAML frontmatter from markdown body.

    Returns (frontmatter_dict, markdown_body).
    Raises ValueError if frontmatter is missing or malformed.
    """
    trimmed = content.strip()
    if not trimmed.startswith("---"):
        raise ValueError("PLAYBOOK.md is missing YAML frontmatter (must start with ---)")

    end_idx = trimmed.index("---", 3) if "---" in trimmed[3:] else -1
    if end_idx == -1:
        raise ValueError("PLAYBOOK.md has malformed YAML frontmatter (missing closing ---)")

    # Find actual end position (index in trimmed, accounting for the 3-char offset)
    end_idx = trimmed.index("---", 3)
    yaml_str = trimmed[3:end_idx].strip()
    body = trimmed[end_idx + 3:].strip()

    parsed = yaml.safe_load(yaml_str)
    if not parsed or not isinstance(parsed, dict):
        raise ValueError("PLAYBOOK.md YAML frontmatter is empty or not a mapping")

    return parsed, body


def _parse_variables(raw: list | None) -> list[VariableDef]:
    if not raw or not isinstance(raw, list):
        return []
    result = []
    for v in raw:
        if not isinstance(v, dict) or "name" not in v:
            continue
        result.append(VariableDef(
            name=v["name"],
            source=v.get("source", ""),
            required=v.get("required", True),
            description=v.get("description", ""),
        ))
    return result


def _parse_steps(raw: list | None) -> list[StepDef]:
    if not raw or not isinstance(raw, list):
        return []
    result = []
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            continue
        result.append(StepDef(
            id=s.get("id", f"step-{i + 1}"),
            order=s.get("order", i + 1),
            title=s.get("title", f"Step {i + 1}"),
            assigned_role=s.get("assignedRole", s.get("assigned_role", "")),
            agent_image=s.get("agentImage", s.get("agent_image", "")),
            timeout_minutes=int(s.get("timeoutMinutes", s.get("timeout_minutes", 30))),
            interactive=bool(s.get("interactive", False)),
            approval=s.get("approval", "approve_only"),
            dependencies=s.get("dependencies", s.get("depends_on", [])) or [],
            description=s.get("description", ""),
            instruction=s.get("instruction", ""),
            required_connections=s.get("required_connections", s.get("requiredConnections", [])) or [],
        ))
    return result


def _parse_step_sections(body: str) -> dict[str, str]:
    """Extract per-step markdown sections from the body.

    Splits on `## Step: {step-id}` headings. Each section spans from its
    heading to the next step heading (or end of body).
    """
    matches = list(_STEP_HEADING_RE.finditer(body))
    if not matches:
        return {}

    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        step_id = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[step_id] = body[start:end].strip()

    return sections


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_playbook(content: str) -> PlaybookDefinition:
    """Parse a PLAYBOOK.md content string into a PlaybookDefinition."""
    fm, body = _parse_frontmatter(content)

    return PlaybookDefinition(
        name=fm.get("name", "Untitled"),
        version=str(fm.get("version", "1.0.0")),
        description=fm.get("description", ""),
        category=fm.get("category", ""),
        schema_version=str(fm.get("schemaVersion", fm.get("schema_version", "v2"))),
        trigger=fm.get("trigger", {}),
        participants=fm.get("participants", []),
        variables=_parse_variables(fm.get("variables")),
        steps=_parse_steps(fm.get("steps")),
        markdown_body=body,
        step_sections=_parse_step_sections(body),
    )


def parse_playbook_file(path: str) -> PlaybookDefinition:
    """Read a PLAYBOOK.md file and parse it."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return parse_playbook(content)
