"""Template Hydration — resolves {{variable}} placeholders in PLAYBOOK.md.

Resolves variable sources against a nested context dict (org data, run inputs,
role members) and substitutes {{variable_name}} placeholders in the markdown body.
Writes the hydrated result to /shared/PLAYBOOK_HYDRATED.md.
"""

from __future__ import annotations

import os
import re
from typing import Any

from src.playbook_parser import PlaybookDefinition, VariableDef


# Match {{variable_name}} with optional whitespace inside braces
_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


# ---------------------------------------------------------------------------
# Variable resolution
# ---------------------------------------------------------------------------


def _resolve_dot_path(context: dict, path: str) -> Any:
    """Traverse a nested dict using a dot-separated path.

    Example: _resolve_dot_path({"org": {"name": "Acme"}}, "org.name") -> "Acme"
    Returns None if any segment is missing.
    """
    current: Any = context
    for segment in path.split("."):
        if isinstance(current, dict):
            current = current.get(segment)
        else:
            return None
        if current is None:
            return None
    return current


def resolve_variables(
    variables: list[VariableDef],
    context: dict,
) -> dict[str, str]:
    """Resolve each variable's source path against the context dict.

    Returns a flat dict of {variable_name: resolved_value_as_string}.
    Raises ValueError for required variables that can't be resolved.
    """
    resolved: dict[str, str] = {}

    for var in variables:
        value = _resolve_dot_path(context, var.source) if var.source else None

        if value is None:
            if var.required:
                raise ValueError(
                    f"Required variable '{var.name}' could not be resolved "
                    f"(source: '{var.source}')"
                )
            continue

        # Convert to string representation
        if isinstance(value, list):
            # For member lists, join emails/names
            parts = []
            for item in value:
                if isinstance(item, dict):
                    parts.append(item.get("email", item.get("displayName", str(item))))
                else:
                    parts.append(str(item))
            resolved[var.name] = ", ".join(parts)
        elif isinstance(value, dict):
            resolved[var.name] = str(value)
        else:
            resolved[var.name] = str(value)

    return resolved


# ---------------------------------------------------------------------------
# Template substitution
# ---------------------------------------------------------------------------


def hydrate_template(content: str, resolved: dict[str, str]) -> str:
    """Replace all {{variable_name}} occurrences in content with resolved values.

    Unresolved placeholders are left as-is (they may be optional or for later use).
    """
    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        return resolved.get(var_name, match.group(0))

    return _VAR_RE.sub(replacer, content)


# ---------------------------------------------------------------------------
# Main hydration entry point
# ---------------------------------------------------------------------------


def hydrate_playbook(
    playbook: PlaybookDefinition,
    context: dict,
    output_path: str = "/shared/PLAYBOOK_HYDRATED.md",
) -> dict[str, str]:
    """Resolve variables, hydrate the markdown body, and write the result.

    Returns the resolved variables dict.
    """
    resolved = resolve_variables(playbook.variables, context)

    hydrated_body = hydrate_template(playbook.markdown_body, resolved)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(hydrated_body)

    return resolved
