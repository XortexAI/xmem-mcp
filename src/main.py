"""
XMem MCP Server — exposes XMem memory + scanner + code operations as MCP tools.

Uses the XMem REST API (src/api) as its backend.
Configure XMEM_API_URL and (optionally) XMEM_API_KEY
in the environment or .env file.

Tools exposed:
    Memory:
      save_memory        — ingest a conversation turn into long-term memory
    Code Intelligence (11 native tools, e.g.):
      search_symbols       — semantic search across functions/classes
      impact_analysis      — see callers/callees of a symbol
      read_symbol_code     — get raw code for a function/class
      get_directory_summary— see what a folder does
      list_indexed_repos   — list repos you have scanned
      browse_community_catalog — browse publicly shared code indexes
"""

from __future__ import annotations

import asyncio
import os

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from scanner_tools import register_scanner_tools

load_dotenv()

XMEM_API_URL = os.getenv("XMEM_API_URL", "http://localhost:8000")
XMEM_API_KEY = os.getenv("XMEM_API_KEY", "")
DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "mcp_user")


_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Get the global HTTP client, creating it if needed."""
    global _http_client
    if _http_client is None:
        headers = {"Content-Type": "application/json"}
        if XMEM_API_KEY:
            headers["Authorization"] = f"Bearer {XMEM_API_KEY}"
        _http_client = httpx.AsyncClient(
            base_url=XMEM_API_URL, headers=headers, timeout=120,
        )
    return _http_client


mcp = FastMCP(
    "xmem-mcp",
    description=(
        "MCP server for long-term memory storage, retrieval, "
        "and code intelligence with XMem. Provides memory tools "
        "(save, search, retrieve) and native code retrieval tools "
        "(search_symbols, impact_analysis, read_file_code, etc)."
    ),
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", "8050")),
)


# ═══════════════════════════════════════════════════════════════════════════
# Memory Tools (existing)
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
async def save_memory(
    text: str,
    user_id: str = "",
    agent_response: str = "",
) -> str:
    """Save information to long-term memory.

    Stores the provided text through XMem's ingest pipeline which
    automatically classifies, extracts profiles, temporal events,
    and summaries.

    Args:
        text: The user message / information to memorize
        user_id: User identifier (defaults to server-configured default)
        agent_response: Optional assistant reply for richer summary extraction
    """
    client = _get_client()
    uid = user_id or DEFAULT_USER_ID

    try:
        resp = await client.post("/v1/memory/ingest", json={
            "user_query": text,
            "agent_response": agent_response,
            "user_id": uid,
        })
        resp.raise_for_status()
        body = resp.json()

        if body.get("status") == "error":
            return f"Error: {body.get('error', 'unknown')}"

        data = body.get("data", {})
        parts = [f"Memory saved (model={data.get('model', '?')})"]

        for domain in ("profile", "temporal", "summary"):
            d = data.get(domain)
            if d and d.get("operations"):
                ops = d["operations"]
                parts.append(
                    f"  {domain}: {len(ops)} ops, "
                    f"confidence={d.get('confidence', 0):.1%}"
                )

        return "\n".join(parts)

    except httpx.HTTPStatusError as exc:
        return f"API error ({exc.response.status_code}): {exc.response.text[:200]}"
    except Exception as exc:
        return f"Error saving memory: {exc}"


@mcp.tool()
async def search_memories(
    query: str,
    user_id: str = "",
    top_k: int = 10,
    domains: str = "profile,temporal,summary",
) -> str:
    """Search stored memories using semantic similarity.

    Returns raw matching records from the specified memory domains
    without generating an LLM answer.

    Args:
        query:   Natural-language search query
        user_id: User identifier
        top_k:   Maximum results per domain
        domains: Comma-separated list of domains to search (profile, temporal, summary)
    """
    client = _get_client()
    uid = user_id or DEFAULT_USER_ID
    domain_list = [d.strip() for d in domains.split(",") if d.strip()]

    try:
        resp = await client.post("/v1/memory/search", json={
            "query": query,
            "user_id": uid,
            "top_k": top_k,
            "domains": domain_list,
        })
        resp.raise_for_status()
        body = resp.json()

        if body.get("status") == "error":
            return f"Error: {body.get('error', 'unknown')}"

        results = body.get("data", {}).get("results", [])
        if not results:
            return "No memories found matching that query."

        lines = []
        for i, r in enumerate(results, 1):
            score = f" (score: {r['score']:.2f})" if r.get("score") else ""
            lines.append(f"{i}. [{r['domain']}]{score} {r['content']}")
        return "\n".join(lines)

    except httpx.HTTPStatusError as exc:
        return f"API error ({exc.response.status_code}): {exc.response.text[:200]}"
    except Exception as exc:
        return f"Error searching memories: {exc}"


@mcp.tool()
async def retrieve_answer(
    query: str,
    user_id: str = "",
    top_k: int = 5,
) -> str:
    """Answer a question using stored memories.

    Retrieves relevant memories and generates an LLM answer grounded
    in the user's stored knowledge.

    Args:
        query:   The question to answer
        user_id: User identifier
        top_k:   Number of source records to consider
    """
    client = _get_client()
    uid = user_id or DEFAULT_USER_ID

    try:
        resp = await client.post("/v1/memory/retrieve", json={
            "query": query,
            "user_id": uid,
            "top_k": top_k,
        })
        resp.raise_for_status()
        body = resp.json()

        if body.get("status") == "error":
            return f"Error: {body.get('error', 'unknown')}"

        data = body.get("data", {})
        answer = data.get("answer", "No answer generated.")
        sources = data.get("sources", [])

        parts = [answer]
        if sources:
            parts.append(f"\n--- Sources ({len(sources)}) ---")
            for s in sources[:5]:
                parts.append(f"  [{s['domain']}] {s['content'][:120]}")

        return "\n".join(parts)

    except httpx.HTTPStatusError as exc:
        return f"API error ({exc.response.status_code}): {exc.response.text[:200]}"
    except Exception as exc:
        return f"Error retrieving answer: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# Code Intelligence Tools
# ═══════════════════════════════════════════════════════════════════════════

register_scanner_tools(mcp, _get_client, DEFAULT_USER_ID)


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════


async def main():
    transport = os.getenv("TRANSPORT", "sse")
    if transport == "sse":
        await mcp.run_sse_async()
    else:
        await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
