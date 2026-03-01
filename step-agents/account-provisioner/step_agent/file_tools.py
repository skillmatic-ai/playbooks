"""File Tools — read/write operations on the shared PVC (/shared).

Provides helpers for step agents to read context files, write intermediate
results, and produce completion reports on the shared persistent volume.
"""

from __future__ import annotations

import os

SHARED_ROOT = "/shared"


def read_shared_file(path: str) -> str:
    """Read a file from the shared PVC.

    Args:
        path: Relative path under /shared (e.g., "PLAYBOOK_HYDRATED.md")

    Returns:
        File contents as a string.

    Raises:
        FileNotFoundError: If the file doesn't exist.
    """
    full_path = os.path.join(SHARED_ROOT, path)
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


def write_shared_file(path: str, content: str) -> str:
    """Write a file to the shared PVC, creating directories as needed.

    Args:
        path: Relative path under /shared (e.g., "artifacts/output.json")
        content: File content to write.

    Returns:
        The full absolute path of the written file.
    """
    full_path = os.path.join(SHARED_ROOT, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    return full_path


def write_report(step_id: str, content: str) -> str:
    """Write a step completion report to /shared/results/{stepId}/report.md.

    Args:
        step_id: The step identifier.
        content: Report content (markdown).

    Returns:
        The full absolute path of the written report.
    """
    return write_shared_file(f"results/{step_id}/report.md", content)
