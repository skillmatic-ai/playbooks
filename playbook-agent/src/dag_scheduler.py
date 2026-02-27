"""DAG Scheduler — dependency graph validation and ready-step computation.

Provides:
  - validate_dag(): Cycle detection and reference validation at startup.
  - get_ready_steps(): Returns launchable steps based on current completion state.
  - get_transitive_dependents(): BFS for failure cascade (skip downstream).
  - is_blocked(): Checks if a step can never run due to failed dependencies.

No external dependencies beyond the project's own playbook_parser.StepDef.
"""

from __future__ import annotations

from src.playbook_parser import StepDef


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CyclicDependencyError(Exception):
    """Raised when the step dependency graph contains a cycle."""

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = cycle
        super().__init__(f"Cyclic dependency detected: {' -> '.join(cycle)}")


# ---------------------------------------------------------------------------
# DAG validation
# ---------------------------------------------------------------------------


def _find_cycle(steps: list[StepDef]) -> list[str]:
    """DFS-based cycle finder.  Returns a list of step IDs forming the cycle."""
    adj: dict[str, list[str]] = {s.id: list(s.dependencies) for s in steps}
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {s.id: WHITE for s in steps}
    parent: dict[str, str | None] = {}

    def dfs(node: str) -> list[str] | None:
        color[node] = GRAY
        for dep in adj[node]:
            if color[dep] == GRAY:
                # Back-edge → cycle found.  Trace the path.
                cycle = [dep, node]
                current = node
                while parent.get(current) and parent[current] != dep:
                    current = parent[current]
                    cycle.append(current)
                cycle.reverse()
                return cycle
            if color[dep] == WHITE:
                parent[dep] = node
                result = dfs(dep)
                if result:
                    return result
        color[node] = BLACK
        return None

    for step in steps:
        if color[step.id] == WHITE:
            result = dfs(step.id)
            if result:
                return result
    return ["unknown"]


def validate_dag(steps: list[StepDef]) -> None:
    """Validate that the step dependency graph is a valid DAG.

    Raises:
        CyclicDependencyError: if a cycle is detected.
        ValueError: if a dependency references a non-existent step ID.
    """
    step_ids = {s.id for s in steps}

    # Check for references to non-existent steps
    for step in steps:
        for dep in step.dependencies:
            if dep not in step_ids:
                raise ValueError(
                    f"Step '{step.id}' depends on '{dep}', which does not exist. "
                    f"Valid step IDs: {sorted(step_ids)}"
                )

    # Kahn's algorithm — topological sort via in-degree counting
    in_degree: dict[str, int] = {s.id: 0 for s in steps}
    dependents: dict[str, list[str]] = {s.id: [] for s in steps}

    for step in steps:
        for dep in step.dependencies:
            dependents[dep].append(step.id)
            in_degree[step.id] += 1

    queue = [sid for sid, deg in in_degree.items() if deg == 0]
    sorted_count = 0

    while queue:
        node = queue.pop(0)
        sorted_count += 1
        for dependent in dependents[node]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if sorted_count < len(steps):
        cycle = _find_cycle(steps)
        raise CyclicDependencyError(cycle)


# ---------------------------------------------------------------------------
# Ready-step computation
# ---------------------------------------------------------------------------


def get_ready_steps(
    steps: list[StepDef],
    completed: set[str],
    failed: set[str],
    running: set[str],
) -> list[StepDef]:
    """Return steps that are ready to launch.

    A step is ready when:
      1. It is not already completed, failed, running, or blocked.
      2. ALL its dependencies are in the ``completed`` set.

    Steps with a dependency in ``failed`` (which should include skipped IDs)
    will never become ready — the orchestrator handles skipping them.

    Returns steps sorted by ``order`` for deterministic launch ordering.
    """
    done = completed | failed | running
    ready = []
    for step in steps:
        if step.id in done:
            continue
        if all(dep in completed for dep in step.dependencies):
            ready.append(step)
    return sorted(ready, key=lambda s: s.order)


# ---------------------------------------------------------------------------
# Failure cascade
# ---------------------------------------------------------------------------


def get_transitive_dependents(step_id: str, steps: list[StepDef]) -> set[str]:
    """Return all step IDs that transitively depend on ``step_id``.

    Uses BFS over the "enables" adjacency (step → steps that depend on it).
    Used to skip all downstream steps when a step fails.
    """
    dependents: dict[str, list[str]] = {s.id: [] for s in steps}
    for step in steps:
        for dep in step.dependencies:
            dependents[dep].append(step.id)

    visited: set[str] = set()
    queue = [step_id]
    while queue:
        current = queue.pop(0)
        for dep_id in dependents.get(current, []):
            if dep_id not in visited:
                visited.add(dep_id)
                queue.append(dep_id)
    return visited


def is_blocked(step_id: str, steps: list[StepDef], failed: set[str]) -> bool:
    """Check whether a step is blocked because one of its dependencies failed."""
    step_map = {s.id: s for s in steps}
    step = step_map.get(step_id)
    if step is None:
        return True
    return any(dep in failed for dep in step.dependencies)
