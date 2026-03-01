"""Skill Loader — discovers and parses SKILL.md files following the Agent Skills standard.

Scans the skills directory for SKILL.md files, parses YAML frontmatter (name,
description) and extracts the markdown body as agent instructions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class SkillDefinition:
    name: str
    description: str
    body: str  # full markdown body (used as system prompt for LLM agents)


def _parse_skill_md(content: str) -> SkillDefinition:
    """Parse a SKILL.md content string into a SkillDefinition."""
    trimmed = content.strip()
    if not trimmed.startswith("---"):
        raise ValueError("SKILL.md is missing YAML frontmatter (must start with ---)")

    end_idx = trimmed.find("---", 3)
    if end_idx == -1:
        raise ValueError("SKILL.md has malformed YAML frontmatter (missing closing ---)")

    yaml_str = trimmed[3:end_idx].strip()
    body = trimmed[end_idx + 3:].strip()

    parsed = yaml.safe_load(yaml_str)
    if not parsed or not isinstance(parsed, dict):
        raise ValueError("SKILL.md YAML frontmatter is empty or not a mapping")

    return SkillDefinition(
        name=parsed.get("name", "unnamed"),
        description=parsed.get("description", ""),
        body=body,
    )


def load_skill(skills_dir: str = "/app/skills") -> SkillDefinition:
    """Find and parse the first SKILL.md in the skills directory.

    Scans skills_dir for subdirectories containing SKILL.md.
    Returns the parsed SkillDefinition.
    Raises FileNotFoundError if no SKILL.md is found.
    """
    skills_path = Path(skills_dir)
    if not skills_path.exists():
        raise FileNotFoundError(f"Skills directory not found: {skills_dir}")

    # Scan subdirectories for SKILL.md
    for subdir in sorted(skills_path.iterdir()):
        if subdir.is_dir():
            skill_file = subdir / "SKILL.md"
            if skill_file.exists():
                content = skill_file.read_text(encoding="utf-8")
                return _parse_skill_md(content)

    # Also check for SKILL.md directly in skills_dir
    direct = skills_path / "SKILL.md"
    if direct.exists():
        content = direct.read_text(encoding="utf-8")
        return _parse_skill_md(content)

    raise FileNotFoundError(f"No SKILL.md found in {skills_dir}")
