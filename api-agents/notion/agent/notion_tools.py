"""notion_tools.py — Tool functions for interacting with the Notion API.

Each function takes an authenticated Notion client and performs a single
API operation.  These are registered as LLM tool definitions for the
Claude tool-use loop in main.py.
"""

from __future__ import annotations

from typing import Any


def create_page(
    client,
    *,
    parent_id: str,
    title: str,
    content_blocks: list[dict] | None = None,
    properties: dict | None = None,
    is_database_item: bool = False,
) -> dict:
    """Create a new page (or database item) in Notion.

    Args:
        client: Authenticated notion_client.Client.
        parent_id: The ID of the parent page or database.
        title: Title of the new page.
        content_blocks: Optional list of Notion block objects for page body.
        properties: Optional dict of property values (for database items).
        is_database_item: If True, parent is a database (not a page).

    Returns:
        The created page object (dict).
    """
    parent = (
        {"database_id": parent_id}
        if is_database_item
        else {"page_id": parent_id}
    )

    page_properties: dict[str, Any] = properties or {}
    if "title" not in page_properties and "Name" not in page_properties:
        page_properties["title"] = {
            "title": [{"text": {"content": title}}]
        }

    kwargs: dict[str, Any] = {
        "parent": parent,
        "properties": page_properties,
    }
    if content_blocks:
        kwargs["children"] = content_blocks

    return client.pages.create(**kwargs)


def update_page(
    client,
    *,
    page_id: str,
    properties: dict | None = None,
    archived: bool | None = None,
) -> dict:
    """Update an existing Notion page's properties or archive status."""
    kwargs: dict[str, Any] = {"page_id": page_id}
    if properties:
        kwargs["properties"] = properties
    if archived is not None:
        kwargs["archived"] = archived
    return client.pages.update(**kwargs)


def append_blocks(
    client,
    *,
    page_id: str,
    blocks: list[dict],
) -> dict:
    """Append content blocks to an existing Notion page."""
    return client.blocks.children.append(
        block_id=page_id,
        children=blocks,
    )


def search_pages(
    client,
    *,
    query: str,
    filter_type: str = "page",
    page_size: int = 10,
) -> list[dict]:
    """Search for pages or databases in the workspace."""
    results = client.search(
        query=query,
        filter={"value": filter_type, "property": "object"},
        page_size=page_size,
    )
    return results.get("results", [])


def read_page(client, *, page_id: str) -> dict:
    """Retrieve a page's properties and metadata."""
    return client.pages.retrieve(page_id=page_id)


def read_page_content(client, *, page_id: str) -> list[dict]:
    """Retrieve all content blocks from a page."""
    blocks: list[dict] = []
    cursor = None
    while True:
        kwargs: dict[str, Any] = {"block_id": page_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        response = client.blocks.children.list(**kwargs)
        blocks.extend(response.get("results", []))
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
    return blocks
