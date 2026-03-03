"""skill_composer.py — Compose a unified instruction string for LLM agents.

Combines the agent's base skill (API reference), runtime task skills, and
prior reports from dependency steps into a single system prompt.

Usage:
    from skill_composer import compose_instructions

    instructions = compose_instructions(
        base_skill=ctx.base_skill_prompt,
        task_skills=ctx.skills,
        prior_reports=ctx.prior_reports,
    )
"""

from __future__ import annotations

from skill_fetcher import SkillContent, format_skills_prompt


def compose_instructions(
    base_skill: str,
    task_skills: list[SkillContent],
    prior_reports: str = "",
) -> str:
    """Compose a unified instruction string from base skill, task skills, and prior reports.

    Returns a single string suitable for injection into an LLM system prompt.
    """
    sections: list[str] = []

    # 1. Base skill — the API-specific reference baked into the agent image
    if base_skill:
        sections.append(base_skill)

    # 2. Task skills — fetched from skills_catalog/ at runtime
    task_prompt = format_skills_prompt(task_skills)
    if task_prompt:
        sections.append(
            "# Task Instructions\n\n"
            "The following task-specific skills define what you should accomplish.\n\n"
            + task_prompt
        )

    # 3. Prior reports — context from completed dependency steps
    if prior_reports:
        sections.append(
            "# Context from Previous Steps\n\n"
            "The following reports were produced by earlier steps in this playbook.\n"
            "Use them as context for your work.\n\n"
            + prior_reports
        )

    return "\n\n---\n\n".join(sections)
