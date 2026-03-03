"""main.py — Notion API Agent implementation.

Exposes execute() and resume() for the base_entrypoint lifecycle.
Uses Deep Agents SDK to interact with the Notion API based on task
skill instructions.
"""

from __future__ import annotations

import json
import os

from deepagents import create_deep_agent
from notion_client import Client as NotionClient

from base_entrypoint import AgentContext, AgentResult
from firestore_client import write_event

from . import notion_tools

# ---------------------------------------------------------------------------
# Markdown → Notion blocks converter (simplified)
# ---------------------------------------------------------------------------


def _markdown_to_blocks(markdown: str) -> list[dict]:
    """Convert simple markdown text to Notion block objects.

    Supports: headings (## / ###), bullet lists (- item), and paragraphs.
    """
    blocks: list[dict] = []
    for line in markdown.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### "):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": stripped[4:]}}]},
            })
        elif stripped.startswith("## "):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": stripped[3:]}}]},
            })
        elif stripped.startswith("# "):
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {"rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]},
            })
        elif stripped.startswith("- ") or stripped.startswith("* "):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]},
            })
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": stripped}}]},
            })
    return blocks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_title(page: dict) -> str:
    """Extract the plain-text title from a Notion page object."""
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            title_parts = prop.get("title", [])
            return "".join(t.get("plain_text", "") for t in title_parts)
    return "Untitled"


def _blocks_to_text(blocks: list[dict]) -> str:
    """Convert Notion blocks back to plain text for LLM consumption."""
    lines: list[str] = []
    for block in blocks:
        block_type = block.get("type", "")
        data = block.get(block_type, {})
        rich_text = data.get("rich_text", [])
        text = "".join(t.get("plain_text", "") for t in rich_text)
        if block_type.startswith("heading"):
            level = block_type[-1]
            lines.append(f"{'#' * int(level)} {text}")
        elif block_type == "bulleted_list_item":
            lines.append(f"- {text}")
        elif block_type == "numbered_list_item":
            lines.append(f"1. {text}")
        else:
            lines.append(text)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------

MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")


# ---------------------------------------------------------------------------
# Tool factory — creates Deep Agents tool functions bound to a Notion client
# ---------------------------------------------------------------------------


def _make_tools(client: NotionClient, artifacts: list[dict]) -> list:
    """Create tool functions as closures over the Notion client.

    The artifacts list is mutated by create_page to track created pages.
    """

    def create_page(
        parent_id: str,
        title: str,
        content_markdown: str = "",
        is_database_item: bool = False,
    ) -> str:
        """Create a new page or database item in Notion. Use this to draft documents, PRDs, specs, or any structured content.

        Args:
            parent_id: The ID of the parent page or database.
            title: Title for the new page.
            content_markdown: Markdown content for the page body. Will be converted to Notion blocks.
            is_database_item: Set true if parent_id is a database ID.
        """
        try:
            blocks = _markdown_to_blocks(content_markdown) if content_markdown else None
            result = notion_tools.create_page(
                client,
                parent_id=parent_id,
                title=title,
                content_blocks=blocks,
                is_database_item=is_database_item,
            )
            page_id = result.get("id", "")
            url = result.get("url", "")
            if url:
                artifacts.append({
                    "service": "notion",
                    "type": "page",
                    "title": title,
                    "url": url,
                })
            return json.dumps({"page_id": page_id, "url": url})
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    def update_page(page_id: str, properties: dict | None = None) -> str:
        """Update an existing Notion page's properties.

        Args:
            page_id: The page ID to update.
            properties: Property values to update (Notion property format).
        """
        try:
            result = notion_tools.update_page(client, page_id=page_id, properties=properties)
            return json.dumps({"page_id": result["id"], "url": result.get("url", "")})
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    def append_blocks(page_id: str, content_markdown: str) -> str:
        """Append content blocks to an existing Notion page.

        Args:
            page_id: The page ID to append content to.
            content_markdown: Markdown content to append. Will be converted to Notion blocks.
        """
        try:
            blocks = _markdown_to_blocks(content_markdown) if content_markdown else []
            result = notion_tools.append_blocks(client, page_id=page_id, blocks=blocks)
            return json.dumps({"block_count": len(result.get("results", []))})
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    def search_pages(query: str, page_size: int = 10) -> str:
        """Search for pages in the Notion workspace by keyword.

        Args:
            query: Search query string.
            page_size: Max results to return (default 10).
        """
        try:
            results = notion_tools.search_pages(client, query=query, page_size=page_size)
            pages = [
                {"id": p["id"], "title": _extract_title(p), "url": p.get("url", "")}
                for p in results
            ]
            return json.dumps({"pages": pages, "count": len(pages)})
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    def read_page(page_id: str) -> str:
        """Read a Notion page's content and properties.

        Args:
            page_id: The page ID to read.
        """
        try:
            page = notion_tools.read_page(client, page_id=page_id)
            content = notion_tools.read_page_content(client, page_id=page_id)
            text = _blocks_to_text(content)
            return json.dumps({
                "id": page["id"],
                "title": _extract_title(page),
                "url": page.get("url", ""),
                "content": text[:3000],
            })
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    return [create_page, update_page, append_blocks, search_pages, read_page]


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


def _run_agent_loop(ctx: AgentContext) -> AgentResult:
    """Run the Deep Agents loop against the Notion API."""
    notion = NotionClient(auth=ctx.access_token)
    artifacts: list[dict] = []

    system_prompt = ctx.composed_instructions or ctx.base_skill_prompt
    tools = _make_tools(notion, artifacts)

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
        payload={"message": "Starting Notion task with Deep Agents"},
    )

    result = agent.invoke({"messages": [{"role": "user", "content": user_message}]})

    # Extract final text from last message
    final_text = result["messages"][-1].content
    if not isinstance(final_text, str):
        final_text = str(final_text)

    return AgentResult(
        report_markdown=final_text,
        artifacts=artifacts,
        result_summary=final_text[:200] if final_text else "Notion task completed",
    )


# ---------------------------------------------------------------------------
# Entrypoint exports
# ---------------------------------------------------------------------------


def execute(ctx: AgentContext) -> AgentResult:
    """Execute the Notion agent task."""
    print(f"[notion-agent] Starting execution for step {ctx.step_id}")
    return _run_agent_loop(ctx)


def resume(ctx: AgentContext, checkpoint: dict, user_input: dict) -> AgentResult:
    """Resume after HITL pause."""
    print(f"[notion-agent] Resuming from checkpoint: {checkpoint.get('phase')}")
    return _run_agent_loop(ctx)
