"""main.py — Zendesk API Agent implementation.

Exposes execute() and resume() for the base_entrypoint lifecycle.
Uses Deep Agents SDK to interact with the Zendesk API based on task
skill instructions.
"""

from __future__ import annotations

import json
import os

from deepagents import create_deep_agent

from base_entrypoint import AgentContext, AgentResult
from firestore_client import write_event

from . import zendesk_tools

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------

MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")


# ---------------------------------------------------------------------------
# Tool factory — creates Deep Agents tool functions bound to base_url + token
# ---------------------------------------------------------------------------


def _make_tools(base_url: str, token: str) -> list:
    """Create tool functions as closures over the Zendesk base URL and token."""

    def search_tickets(
        query: str,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page_size: int = 25,
    ) -> str:
        """Search Zendesk tickets using query syntax. Supports status, tags, priority, assignee, and date filters.

        Args:
            query: Zendesk search query (e.g. 'status:open priority:high tags:billing').
            sort_by: Sort field: created_at, updated_at, priority, status.
            sort_order: Sort direction: asc or desc.
            page_size: Number of results (max 100).
        """
        try:
            result = zendesk_tools.search_tickets(
                base_url, token,
                query=query, sort_by=sort_by, sort_order=sort_order, page_size=page_size,
            )
            tickets = result.get("results", [])
            simplified = [
                {
                    "id": t.get("id"),
                    "subject": t.get("subject"),
                    "status": t.get("status"),
                    "priority": t.get("priority"),
                    "tags": t.get("tags", []),
                    "created_at": t.get("created_at"),
                    "description": (t.get("description", "") or "")[:500],
                }
                for t in tickets
            ]
            return json.dumps({"tickets": simplified, "count": result.get("count", 0)})
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    def get_ticket_details(ticket_id: int) -> str:
        """Get full details for a specific Zendesk ticket by ID, including metadata and user info.

        Args:
            ticket_id: The Zendesk ticket ID.
        """
        try:
            result = zendesk_tools.get_ticket_details(base_url, token, ticket_id=ticket_id)
            ticket = result.get("ticket", {})
            return json.dumps({
                "id": ticket.get("id"),
                "subject": ticket.get("subject"),
                "status": ticket.get("status"),
                "priority": ticket.get("priority"),
                "tags": ticket.get("tags", []),
                "created_at": ticket.get("created_at"),
                "updated_at": ticket.get("updated_at"),
                "description": (ticket.get("description", "") or "")[:2000],
                "requester_id": ticket.get("requester_id"),
                "assignee_id": ticket.get("assignee_id"),
                "satisfaction_rating": ticket.get("satisfaction_rating"),
            })
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    def get_ticket_comments(ticket_id: int) -> str:
        """Get all comments/replies on a specific ticket.

        Args:
            ticket_id: The Zendesk ticket ID.
        """
        try:
            comments = zendesk_tools.get_ticket_comments(base_url, token, ticket_id=ticket_id)
            simplified = [
                {
                    "id": c.get("id"),
                    "author_id": c.get("author_id"),
                    "body": (c.get("body", "") or "")[:1000],
                    "public": c.get("public"),
                    "created_at": c.get("created_at"),
                }
                for c in comments
            ]
            return json.dumps({"comments": simplified, "count": len(simplified)})
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    def list_tickets_by_date(
        start_date: str,
        end_date: str | None = None,
        status: str | None = None,
        page_size: int = 25,
    ) -> str:
        """List tickets created within a date range, optionally filtered by status.

        Args:
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format (optional).
            status: Filter by status: new, open, pending, hold, solved, closed.
            page_size: Number of results (max 100).
        """
        try:
            result = zendesk_tools.list_tickets_by_date(
                base_url, token,
                start_date=start_date, end_date=end_date, status=status, page_size=page_size,
            )
            tickets = result.get("results", [])
            simplified = [
                {
                    "id": t.get("id"),
                    "subject": t.get("subject"),
                    "status": t.get("status"),
                    "priority": t.get("priority"),
                    "tags": t.get("tags", []),
                    "created_at": t.get("created_at"),
                }
                for t in tickets
            ]
            return json.dumps({"tickets": simplified, "count": result.get("count", 0)})
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    def export_ticket_data(query: str, max_results: int = 100) -> str:
        """Export ticket data as structured records for analysis. Searches tickets and returns simplified data suitable for clustering, sentiment analysis, or trend analysis.

        Args:
            query: Zendesk search query.
            max_results: Maximum tickets to export (default 100).
        """
        try:
            exported = zendesk_tools.export_ticket_data(
                base_url, token, query=query, max_results=max_results,
            )
            return json.dumps({"tickets": exported, "count": len(exported)})
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    return [search_tickets, get_ticket_details, get_ticket_comments, list_tickets_by_date, export_ticket_data]


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


def _run_agent_loop(ctx: AgentContext) -> AgentResult:
    """Run the Deep Agents loop against the Zendesk API."""
    # Resolve Zendesk base URL from step config or run context
    base_url = (
        ctx.step_config.get("zendesk_url")
        or ctx.run_context.get("zendesk_url")
        or os.environ.get("ZENDESK_URL", "")
    )
    if not base_url:
        return AgentResult(
            report_markdown="Error: No Zendesk URL configured. Set zendesk_url in playbook variables.",
            result_summary="Failed: no Zendesk URL",
        )

    base_url = base_url.rstrip("/")

    system_prompt = ctx.composed_instructions or ctx.base_skill_prompt
    tools = _make_tools(base_url, ctx.access_token)

    agent = create_deep_agent(
        tools=tools,
        system_prompt=system_prompt,
        model=MODEL,
    )

    # Build user message from run context
    run_context = ctx.run_context or {}
    user_message = "Execute the task according to your instructions."
    if run_context:
        context_lines = [f"- {k}: {v}" for k, v in run_context.items() if k != "zendesk_url"]
        if context_lines:
            user_message = (
                "Execute the task with the following context:\n"
                + "\n".join(context_lines)
            )

    write_event(
        ctx.org_id, ctx.run_id, "progress",
        step_id=ctx.step_id,
        payload={"message": "Starting Zendesk analysis with Deep Agents"},
    )

    result = agent.invoke({"messages": [{"role": "user", "content": user_message}]})

    # Extract final text from last message
    final_text = result["messages"][-1].content
    if not isinstance(final_text, str):
        final_text = str(final_text)

    return AgentResult(
        report_markdown=final_text,
        artifacts=[],
        result_summary=final_text[:200] if final_text else "Zendesk analysis completed",
    )


# ---------------------------------------------------------------------------
# Entrypoint exports
# ---------------------------------------------------------------------------


def execute(ctx: AgentContext) -> AgentResult:
    """Execute the Zendesk agent task."""
    print(f"[zendesk-agent] Starting execution for step {ctx.step_id}")
    return _run_agent_loop(ctx)


def resume(ctx: AgentContext, checkpoint: dict, user_input: dict) -> AgentResult:
    """Resume after HITL pause."""
    print(f"[zendesk-agent] Resuming from checkpoint: {checkpoint.get('phase')}")
    return _run_agent_loop(ctx)
