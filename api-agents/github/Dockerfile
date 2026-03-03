# =============================================================================
# GitHub API Agent
# =============================================================================
# Extends the shared API agent base with GitHub API tools.
# =============================================================================

ARG BASE_IMAGE=api-agent-base:latest
FROM ${BASE_IMAGE}

# Install GitHub-specific dependencies
COPY requirements.txt /tmp/requirements-agent.txt
RUN pip install --no-cache-dir -r /tmp/requirements-agent.txt

# Copy agent code
COPY agent/ /app/agent/

# Copy baked-in base skill (GitHub API reference)
COPY base-skill/ /base-skill/

# Set agent module
ENV AGENT_MODULE=agent.main
