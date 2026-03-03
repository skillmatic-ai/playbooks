"""skill_fetcher.py — Fetch task skills from Firestore skills_catalog at runtime.

API agents load task-specific skills (e.g., "prd-template-v2", "jtbd-clustering")
on startup.  Skill IDs are declared in PLAYBOOK.md steps and stored on the
step document.

Usage:
    from skill_fetcher import fetch_skills

    skills = fetch_skills(["prd-template-v2", "jtbd-clustering"])
    # Each skill has: id, name, instructions, references, compatible_apis
"""

from __future__ import annotations

from dataclasses import dataclass, field

import firebase_admin
from firebase_admin import firestore as fs

# ---------------------------------------------------------------------------
# Initialisation (module-level singleton)
# ---------------------------------------------------------------------------

_app: firebase_admin.App | None = None


def _get_db() -> fs.firestore.Client:
    global _app
    if _app is None:
        _app = firebase_admin.initialize_app()
    return fs.client(_app)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class SkillContent:
    """Structured content of a fetched task skill."""
    id: str
    name: str
    description: str = ""
    instructions: str = ""
    references: list[str] = field(default_factory=list)
    compatible_apis: list[str] = field(default_factory=list)
    scripts: list[dict] = field(default_factory=list)
    version: str = ""
    track: str = ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_skills(
    skill_ids: list[str],
    *,
    agent_api: str | None = None,
) -> list[SkillContent]:
    """Fetch task skills from Firestore ``skills_catalog/`` collection.

    Args:
        skill_ids: List of skill document IDs to fetch.
        agent_api: If provided, validates that each skill is compatible
            with this API (``compatible_apis`` field).  Incompatible skills
            are logged and skipped.

    Returns:
        List of SkillContent objects (in the same order as skill_ids,
        missing/incompatible skills omitted).
    """
    if not skill_ids:
        return []

    db = _get_db()
    catalog_ref = db.collection("skills_catalog")

    results: list[SkillContent] = []

    for skill_id in skill_ids:
        doc = catalog_ref.document(skill_id).get()
        if not doc.exists:
            print(f"[skill_fetcher] Skill '{skill_id}' not found in catalog — skipping")
            continue

        data = doc.to_dict() or {}
        compatible = data.get("compatibleApis", [])

        # Compatibility check
        if agent_api and compatible and agent_api not in compatible:
            print(
                f"[skill_fetcher] Skill '{skill_id}' not compatible with "
                f"api '{agent_api}' (supports: {compatible}) — skipping"
            )
            continue

        results.append(SkillContent(
            id=skill_id,
            name=data.get("name", skill_id),
            description=data.get("description", ""),
            instructions=data.get("instructions", ""),
            references=data.get("references", []),
            compatible_apis=compatible,
            scripts=data.get("scripts", []),
            version=data.get("version", ""),
            track=data.get("track", ""),
        ))
        print(f"[skill_fetcher] Loaded skill: {skill_id} ({data.get('name', '')})")

    return results


def format_skills_prompt(skills: list[SkillContent]) -> str:
    """Format fetched skills into a prompt section for the LLM.

    Returns a structured text block that can be injected into the agent's
    system prompt alongside the base skill.
    """
    if not skills:
        return ""

    sections: list[str] = []
    for skill in skills:
        section = f"=== Task Skill: {skill.name} ===\n"
        if skill.description:
            section += f"{skill.description}\n\n"
        if skill.instructions:
            section += f"{skill.instructions}\n"
        if skill.references:
            section += "\nReferences:\n"
            for ref in skill.references:
                section += f"  - {ref}\n"
        sections.append(section)

    return "\n\n".join(sections)
