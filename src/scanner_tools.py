"""
Code Retrieval MCP tools.

Exposes the 11 raw code intelligence tools from the XMem Code Retrieval Pipeline
directly to the MCP client (e.g. ChatGPT, Claude Desktop, Cursor).

This allows the client LLM to autonomously explore the repository natively
without proxying through the backend XMem Agent.
"""

from __future__ import annotations

import httpx
from mcp.server.fastmcp import FastMCP

def register_scanner_tools(
    mcp: FastMCP,
    get_client: callable,
    default_user_id: str,
    check_auth: callable | None = None,
) -> None:
    """Register all 11 granular code query tools on the given MCP server."""

    def _auth_error() -> str | None:
        """Check auth if provided, otherwise allow (for backward compatibility)."""
        if check_auth:
            return check_auth()
        return None

    async def _execute(org_id: str, repo: str, tool_name: str, tool_args: dict, user_id: str) -> str:
        """Helper to invoke the backend POST /v1/code/execute-tool."""
        # Check authentication first
        if auth_err := _auth_error():
            return auth_err

        client = get_client()
        uid = user_id or default_user_id
        try:
            resp = await client.post("/v1/code/execute-tool", json={
                "org_id": org_id,
                "repo": repo,
                "tool_name": tool_name,
                "tool_args": tool_args,
                "user_id": uid,
            })
            if resp.status_code == 403:
                body = resp.json()
                return f"Permission Denied: {body.get('error', 'You do not have access to this indexed repository.')}"
            
            resp.raise_for_status()
            body = resp.json()
            if body.get("status") == "error":
                return f"Error: {body.get('error', 'unknown')}"
                
            records = body.get("data", {}).get("records", [])
            if not records:
                return f"No results found for {tool_name}."
                
            parts = [f"--- Results for {tool_name} ({len(records)}) ---"]
            for r in records:
                domain = r.get("domain", "")
                content = r.get("content", "")
                parts.append(f"[{domain}]\n{content}\n")
            return "\n".join(parts)
            
        except httpx.HTTPStatusError as exc:
            return f"API error ({exc.response.status_code}): {exc.response.text[:200]}"
        except httpx.RequestError as exc:
            return f"Network error connecting to XMem API: {exc}"
        except httpx.TimeoutException as exc:
            return f"Request timed out: {exc}"

    # ── 1. search_symbols ──────────────────────────────────────────────
    @mcp.tool()
    async def search_symbols(
        org_id: str,
        repo: str,
        query: str,
        user_id: str = "",
    ) -> str:
        """Hybrid search across functions/classes/methods by semantic meaning or exact name.
        Uses graph-conditioned retrieval (combines vector similarity, BM25, and call graph signals)."""
        return await _execute(org_id, repo, "search_symbols", {"query": query}, user_id)

    # ── 2. search_files ────────────────────────────────────────────────
    @mcp.tool()
    async def search_files(
        org_id: str,
        repo: str,
        query: str,
        user_id: str = "",
    ) -> str:
        """Search for files by their semantic summary and overall purpose."""
        return await _execute(org_id, repo, "search_files", {"query": query}, user_id)

    # ── 3. search_annotations ──────────────────────────────────────────
    @mcp.tool()
    async def search_annotations(
        org_id: str,
        repo: str,
        query: str,
        user_id: str = "",
    ) -> str:
        """Search team annotations: bug reports, design decisions, warnings attached to code."""
        return await _execute(org_id, repo, "search_annotations", {"query": query}, user_id)

    # ── 4. impact_analysis ─────────────────────────────────────────────
    @mcp.tool()
    async def impact_analysis(
        org_id: str,
        repo: str,
        symbol_name: str,
        depth: int = 2,
        user_id: str = "",
    ) -> str:
        """Graph traversal showing callers, callees, and inheritance for a specific symbol.
        Crucial for answering 'what breaks if I change X?'"""
        return await _execute(org_id, repo, "impact_analysis", {"symbol_name": symbol_name, "depth": depth}, user_id)

    # ── 5. get_file_context ────────────────────────────────────────────
    @mcp.tool()
    async def get_file_context(
        org_id: str,
        repo: str,
        file_path: str,
        user_id: str = "",
    ) -> str:
        """Get the structural context of a file: what symbols it defines and what it imports."""
        return await _execute(org_id, repo, "get_file_context", {"file_path": file_path}, user_id)

    # ── 6. read_symbol_code ────────────────────────────────────────────
    @mcp.tool()
    async def read_symbol_code(
        org_id: str,
        repo: str,
        symbol_name: str,
        file_path: str,
        user_id: str = "",
    ) -> str:
        """Read the EXACT raw source code of a specific function, method, or class."""
        return await _execute(org_id, repo, "read_symbol_code", {"symbol_name": symbol_name, "file_path": file_path}, user_id)

    # ── 7. read_file_code ──────────────────────────────────────────────
    @mcp.tool()
    async def read_file_code(
        org_id: str,
        repo: str,
        file_path: str,
        user_id: str = "",
    ) -> str:
        """Read the ENTIRE raw source code of a specific file."""
        return await _execute(org_id, repo, "read_file_code", {"file_path": file_path}, user_id)

    # ── 8. search_snippets ─────────────────────────────────────────────
    @mcp.tool()
    async def search_snippets(
        org_id: str,
        repo: str,
        query: str,
        user_id: str = "",
    ) -> str:
        """Search the user's personal saved code snippets."""
        return await _execute(org_id, repo, "search_snippets", {"query": query}, user_id)

    # ── 9. get_repo_structure ──────────────────────────────────────────
    @mcp.tool()
    async def get_repo_structure(
        org_id: str,
        repo: str,
        user_id: str = "",
    ) -> str:
        """Get a list of all directories in the repository along with their file counts and summaries."""
        return await _execute(org_id, repo, "get_repo_structure", {}, user_id)

    # ── 10. get_directory_summary ──────────────────────────────────────
    @mcp.tool()
    async def get_directory_summary(
        org_id: str,
        repo: str,
        dir_path: str,
        user_id: str = "",
    ) -> str:
        """Get the semantic summary of what a specific directory does and lists its files."""
        return await _execute(org_id, repo, "get_directory_summary", {"dir_path": dir_path}, user_id)

    # ── 11. get_file_summary ───────────────────────────────────────────
    @mcp.tool()
    async def get_file_summary(
        org_id: str,
        repo: str,
        file_path: str,
        user_id: str = "",
    ) -> str:
        """Get the semantic summary outlining what a specific file is responsible for."""
        return await _execute(org_id, repo, "get_file_summary", {"file_path": file_path}, user_id)

    # ── Extra: list_indexed_repos ──────────────────────────────────────
    @mcp.tool()
    async def list_indexed_repos(
        user_id: str = "",
    ) -> str:
        """List all repositories scanned by you."""
        # Check authentication
        if auth_err := _auth_error():
            return auth_err

        client = get_client()
        uid = user_id or default_user_id
        try:
            resp = await client.get("/v1/scanner/repos", params={"username": uid})
            resp.raise_for_status()
            body = resp.json()
            if body.get("status") == "error":
                return f"Error: {body.get('error', 'unknown')}"
            repos = body.get("repos", [])
            if not repos:
                return "You have not scanned any repositories yet."
            lines = ["Your Scanned Repositories:"]
            for r in repos:
                lines.append(f"  • {r['org']}/{r['repo']} (Phase 1: {r.get('phase1_status')})")
            return "\n".join(lines)
        except httpx.HTTPStatusError as exc:
            return f"API error ({exc.response.status_code}): {exc.response.text[:200]}"
        except httpx.RequestError as exc:
            return f"Network error connecting to XMem API: {exc}"
        except httpx.TimeoutException as exc:
            return f"Request timed out: {exc}"

    # ── Extra: browse_community_catalog ────────────────────────────────
    @mcp.tool()
    async def browse_community_catalog(
        query: str = "",
        limit: int = 20,
        user_id: str = "",
    ) -> str:
        """Browse publicly shared code indexes from the community catalog."""
        # Check authentication
        if auth_err := _auth_error():
            return auth_err

        client = get_client()
        uid = user_id or default_user_id
        try:
            resp = await client.get("/v1/scanner/community", params={
                "username": uid,
                "q": query,
                "sort": "stars",
                "limit": limit,
            })
            resp.raise_for_status()
            body = resp.json()
            items = body.get("items", [])
            total = body.get("total", 0)
            if not items:
                return "No community indexes found."
            lines = [f"Community catalog ({total} total):"]
            for item in items:
                stars = item.get("star_count", 0)
                lines.append(f"  ⭐{stars} {item.get('org_id')}/{item.get('repo')}")
            return "\n".join(lines)
        except httpx.HTTPStatusError as exc:
            return f"API error ({exc.response.status_code}): {exc.response.text[:200]}"
        except httpx.RequestError as exc:
            return f"Network error connecting to XMem API: {exc}"
        except httpx.TimeoutException as exc:
            return f"Request timed out: {exc}"
