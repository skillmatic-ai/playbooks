"""zendesk_tools.py — Tool functions for interacting with the Zendesk API.

Uses httpx directly against the Zendesk REST API v2.
Each function takes a base_url and access_token and performs a single operation.
"""

from __future__ import annotations

import httpx


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def search_tickets(
    base_url: str,
    token: str,
    *,
    query: str,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    page_size: int = 25,
) -> dict:
    """Search tickets using Zendesk search API.

    Args:
        base_url: Zendesk subdomain URL (e.g. https://company.zendesk.com)
        token: OAuth access token.
        query: Zendesk search query (e.g. 'type:ticket status:open tags:bug').
        sort_by: Sort field (created_at, updated_at, priority, status).
        sort_order: asc or desc.
        page_size: Results per page (max 100).

    Returns:
        Dict with 'results', 'count', and pagination info.
    """
    resp = httpx.get(
        f"{base_url}/api/v2/search.json",
        headers=_headers(token),
        params={
            "query": f"type:ticket {query}",
            "sort_by": sort_by,
            "sort_order": sort_order,
            "per_page": min(page_size, 100),
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_ticket_details(
    base_url: str,
    token: str,
    *,
    ticket_id: int,
) -> dict:
    """Get full details for a specific ticket including comments."""
    resp = httpx.get(
        f"{base_url}/api/v2/tickets/{ticket_id}.json",
        headers=_headers(token),
        params={"include": "users,groups"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_ticket_comments(
    base_url: str,
    token: str,
    *,
    ticket_id: int,
    page_size: int = 50,
) -> list[dict]:
    """Get comments for a specific ticket."""
    resp = httpx.get(
        f"{base_url}/api/v2/tickets/{ticket_id}/comments.json",
        headers=_headers(token),
        params={"per_page": min(page_size, 100)},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("comments", [])


def list_tickets_by_date(
    base_url: str,
    token: str,
    *,
    start_date: str,
    end_date: str | None = None,
    status: str | None = None,
    page_size: int = 25,
) -> dict:
    """List tickets within a date range."""
    query_parts = [f"created>{start_date}"]
    if end_date:
        query_parts.append(f"created<{end_date}")
    if status:
        query_parts.append(f"status:{status}")
    query = " ".join(query_parts)

    return search_tickets(
        base_url, token,
        query=query,
        sort_by="created_at",
        page_size=page_size,
    )


def export_ticket_data(
    base_url: str,
    token: str,
    *,
    query: str,
    fields: list[str] | None = None,
    max_results: int = 100,
) -> list[dict]:
    """Search and export ticket data as structured records.

    Returns a list of simplified ticket dicts suitable for analysis.
    """
    result = search_tickets(base_url, token, query=query, page_size=min(max_results, 100))
    tickets = result.get("results", [])

    default_fields = ["id", "subject", "status", "priority", "tags", "created_at", "updated_at"]
    selected_fields = fields or default_fields

    exported: list[dict] = []
    for ticket in tickets[:max_results]:
        record: dict = {}
        for f in selected_fields:
            record[f] = ticket.get(f)
        exported.append(record)

    return exported
