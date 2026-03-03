"""main.py — GitHub API Agent implementation.

Exposes execute() and resume() for the base_entrypoint lifecycle.
Uses Deep Agents SDK to interact with the GitHub API based on task
skill instructions.
"""

from __future__ import annotations

import json
import os

from deepagents import create_deep_agent

from base_entrypoint import AgentContext, AgentResult
from firestore_client import write_event

from . import github_tools

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------

MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")


# ---------------------------------------------------------------------------
# Tool factory — creates Deep Agents tool functions bound to an access token
# ---------------------------------------------------------------------------


def _make_tools(token: str) -> list:
    """Create tool functions as closures over the GitHub access token."""

    def search_code(query: str, page_size: int = 10) -> str:
        """Search code across GitHub repositories. Supports filename, path, language, and content filters.

        Args:
            query: GitHub code search query (e.g. 'class AuthService repo:org/repo language:python').
            page_size: Number of results (max 100).
        """
        try:
            result = github_tools.search_code(token, query=query, page_size=page_size)
            items = result.get("items", [])
            simplified = [
                {
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "repository": item.get("repository", {}).get("full_name"),
                    "html_url": item.get("html_url"),
                    "score": item.get("score"),
                }
                for item in items
            ]
            return json.dumps({"matches": simplified, "total_count": result.get("total_count", 0)})
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    def get_repo_structure(owner: str, repo: str, path: str = "", ref: str = "main") -> str:
        """List files and directories in a repository path. Use to explore repo structure.

        Args:
            owner: Repository owner (user or org).
            repo: Repository name.
            path: Path within the repo (empty string for root).
            ref: Branch or commit ref (default: main).
        """
        try:
            items = github_tools.get_repo_structure(
                token, owner=owner, repo=repo, path=path, ref=ref,
            )
            simplified = [
                {
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "path": item.get("path"),
                    "size": item.get("size"),
                }
                for item in items
            ]
            return json.dumps({"items": simplified, "count": len(simplified)})
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    def read_file_content(owner: str, repo: str, path: str, ref: str = "main") -> str:
        """Read the content of a specific file from a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            path: File path within the repo.
            ref: Branch or commit ref.
        """
        try:
            result = github_tools.read_file_content(
                token, owner=owner, repo=repo, path=path, ref=ref,
            )
            content = result.get("content", "")
            if len(content) > 5000:
                content = content[:5000] + "\n\n... [truncated, file too large]"
                result["content"] = content
                result["truncated"] = True
            return json.dumps(result)
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    def list_recent_prs(owner: str, repo: str, state: str = "all", page_size: int = 10) -> str:
        """List recent pull requests for a repository, sorted by update time.

        Args:
            owner: Repository owner.
            repo: Repository name.
            state: PR state filter: open, closed, all.
            page_size: Number of results (max 100).
        """
        try:
            prs = github_tools.list_recent_prs(
                token, owner=owner, repo=repo, state=state, page_size=page_size,
            )
            simplified = [
                {
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "state": pr.get("state"),
                    "user": pr.get("user", {}).get("login"),
                    "created_at": pr.get("created_at"),
                    "updated_at": pr.get("updated_at"),
                    "html_url": pr.get("html_url"),
                    "additions": pr.get("additions"),
                    "deletions": pr.get("deletions"),
                    "changed_files": pr.get("changed_files"),
                }
                for pr in prs
            ]
            return json.dumps({"pull_requests": simplified, "count": len(simplified)})
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    def get_repo_info(owner: str, repo: str) -> str:
        """Get repository metadata including description, stars, language, default branch, and contribution stats.

        Args:
            owner: Repository owner.
            repo: Repository name.
        """
        try:
            info = github_tools.get_repo_info(token, owner=owner, repo=repo)
            languages = github_tools.list_repo_languages(token, owner=owner, repo=repo)
            return json.dumps({
                "full_name": info.get("full_name"),
                "description": info.get("description"),
                "default_branch": info.get("default_branch"),
                "language": info.get("language"),
                "languages": languages,
                "stargazers_count": info.get("stargazers_count"),
                "forks_count": info.get("forks_count"),
                "open_issues_count": info.get("open_issues_count"),
                "size": info.get("size"),
                "created_at": info.get("created_at"),
                "updated_at": info.get("updated_at"),
                "html_url": info.get("html_url"),
            })
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    return [search_code, get_repo_structure, read_file_content, list_recent_prs, get_repo_info]


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


def _run_agent_loop(ctx: AgentContext) -> AgentResult:
    """Run the Deep Agents loop against the GitHub API."""
    system_prompt = ctx.composed_instructions or ctx.base_skill_prompt
    tools = _make_tools(ctx.access_token)

    agent = create_deep_agent(
        tools=tools,
        system_prompt=system_prompt,
        model=MODEL,
    )

    # Build user message from run context
    run_context = ctx.run_context or {}
    user_message = "Execute the task according to your instructions."
    if run_context:
        context_lines = [f"- {k}: {v}" for k, v in run_context.items()]
        if context_lines:
            user_message = (
                "Execute the task with the following context:\n"
                + "\n".join(context_lines)
            )

    write_event(
        ctx.org_id, ctx.run_id, "progress",
        step_id=ctx.step_id,
        payload={"message": "Starting GitHub analysis with Deep Agents"},
    )

    result = agent.invoke({"messages": [{"role": "user", "content": user_message}]})

    # Extract final text from last message
    final_text = result["messages"][-1].content
    if not isinstance(final_text, str):
        final_text = str(final_text)

    return AgentResult(
        report_markdown=final_text,
        artifacts=[],
        result_summary=final_text[:200] if final_text else "GitHub analysis completed",
    )


# ---------------------------------------------------------------------------
# Entrypoint exports
# ---------------------------------------------------------------------------


def execute(ctx: AgentContext) -> AgentResult:
    """Execute the GitHub agent task."""
    print(f"[github-agent] Starting execution for step {ctx.step_id}")
    return _run_agent_loop(ctx)


def resume(ctx: AgentContext, checkpoint: dict, user_input: dict) -> AgentResult:
    """Resume after HITL pause."""
    print(f"[github-agent] Resuming from checkpoint: {checkpoint.get('phase')}")
    return _run_agent_loop(ctx)
