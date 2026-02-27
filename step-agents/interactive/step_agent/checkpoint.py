"""Checkpoint helpers — save/load/clear JSON state files on the shared PVC.

Checkpoint files live at /shared/checkpoints/step-{stepId}.json and contain
the execution phase, pending questionId, and any accumulated state the agent
needs to resume after a HITL pause.
"""

from __future__ import annotations

import json
import os

CHECKPOINT_DIR = "/shared/checkpoints"


def save_checkpoint(step_id: str, data: dict) -> str:
    """Write a checkpoint file. Returns the file path."""
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    path = os.path.join(CHECKPOINT_DIR, f"step-{step_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def load_checkpoint(step_id: str) -> dict | None:
    """Load a checkpoint file. Returns None if no checkpoint exists."""
    path = os.path.join(CHECKPOINT_DIR, f"step-{step_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def clear_checkpoint(step_id: str) -> None:
    """Remove a checkpoint file (called on step completion)."""
    path = os.path.join(CHECKPOINT_DIR, f"step-{step_id}.json")
    if os.path.exists(path):
        os.remove(path)
