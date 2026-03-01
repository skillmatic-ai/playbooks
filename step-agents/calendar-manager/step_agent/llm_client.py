"""LLM Client — Generate text via Anthropic Claude API.

Reads the AI API key from Firestore org secrets and uses the anthropic
Python SDK to make messages.create() calls. Emits a Firestore event
before each LLM call for observability.

Usage:
    from step_agent.llm_client import generate

    text = generate(
        org_id, run_id, step_id,
        system_prompt="You are an HR onboarding specialist.",
        user_prompt="Draft a welcome email for Jane Doe joining Acme Corp.",
    )
"""

import anthropic

from step_agent.firestore_client import write_event
from step_agent.secrets_client import read_ai_config


def generate(
    org_id: str,
    run_id: str,
    step_id: str,
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    model: str | None = None,
) -> str:
    """Generate text using Claude via the Anthropic SDK.

    Reads the API key from Firestore org secrets on every call (no caching —
    keys may rotate). Emits an agent_thinking event for observability.

    Args:
        org_id: Organization ID (for reading AI config from Firestore).
        run_id: Playbook run ID (for emitting events).
        step_id: Step ID (for emitting events).
        system_prompt: The system message for Claude.
        user_prompt: The user message for Claude.
        max_tokens: Maximum tokens in the response. Default 4096.
        temperature: Sampling temperature. Default 0.7.
        model: Override the model from Firestore config. Optional.

    Returns:
        The generated text content.

    Raises:
        ValueError: If AI config is missing from Firestore.
        anthropic.APIError: If the API call fails.
    """
    ai_config = read_ai_config(org_id)
    resolved_model = model or ai_config.get("model", "claude-sonnet-4-20250514")

    write_event(
        org_id, run_id, "agent_thinking",
        step_id=step_id,
        payload={
            "message": f"Calling {resolved_model} (max_tokens={max_tokens})",
            "model": resolved_model,
        },
    )

    client = anthropic.Anthropic(api_key=ai_config["apiKey"])

    response = client.messages.create(
        model=resolved_model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Extract text from the response
    text_blocks = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_blocks)
