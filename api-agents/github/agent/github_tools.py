"""github_tools.py — Tool functions for interacting with the GitHub REST API.

Uses httpx directly against the GitHub REST API v3.
Each function takes an access_token and performs a single operation.
"""

from __future__ import annotations

import base64

import httpx

API_BASE = "https://api.github.com"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def search_code(
    token: str,
    *,
    query: str,
    page_size: int = 10,
) -> dict:
    """Search code across repositories.

    Args:
        token: GitHub OAuth access token.
        query: GitHub code search query (e.g. 'class AuthService repo:org/repo').
        page_size: Results per page (max 100).

    Returns:
        Dict with 'items' (code matches), 'total_count'.
    """
    resp = httpx.get(
        f"{API_BASE}/search/code",
        headers=_headers(token),
        params={"q": query, "per_page": min(page_size, 100)},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_repo_structure(
    token: str,
    *,
    owner: str,
    repo: str,
    path: str = "",
    ref: str = "main",
) -> list[dict]:
    """List files and directories in a repository path.

    Returns a list of items with name, type (file/dir), path, and size.
    """
    params = {"ref": ref}
    url = f"{API_BASE}/repos/{owner}/{repo}/contents/{path}"
    resp = httpx.get(url, headers=_headers(token), params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # Single file returns a dict, directory returns a list
    if isinstance(data, dict):
        return [data]
    return data


def read_file_content(
    token: str,
    *,
    owner: str,
    repo: str,
    path: str,
    ref: str = "main",
) -> dict:
    """Read a file's content from a repository.

    Returns dict with 'content' (decoded text), 'size', 'sha'.
    """
    url = f"{API_BASE}/repos/{owner}/{repo}/contents/{path}"
    resp = httpx.get(
        url,
        headers=_headers(token),
        params={"ref": ref},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    content = ""
    if data.get("encoding") == "base64" and data.get("content"):
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")

    return {
        "path": data.get("path", path),
        "size": data.get("size", 0),
        "sha": data.get("sha", ""),
        "content": content,
    }


def list_recent_prs(
    token: str,
    *,
    owner: str,
    repo: str,
    state: str = "all",
    page_size: int = 10,
) -> list[dict]:
    """List recent pull requests for a repository."""
    resp = httpx.get(
        f"{API_BASE}/repos/{owner}/{repo}/pulls",
        headers=_headers(token),
        params={
            "state": state,
            "sort": "updated",
            "direction": "desc",
            "per_page": min(page_size, 100),
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def list_repo_languages(
    token: str,
    *,
    owner: str,
    repo: str,
) -> dict:
    """Get the language breakdown for a repository.

    Returns a dict mapping language names to byte counts.
    """
    resp = httpx.get(
        f"{API_BASE}/repos/{owner}/{repo}/languages",
        headers=_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_repo_info(
    token: str,
    *,
    owner: str,
    repo: str,
) -> dict:
    """Get repository metadata (description, stats, default branch, etc.)."""
    resp = httpx.get(
        f"{API_BASE}/repos/{owner}/{repo}",
        headers=_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
