"""
XMem MCP Server — exposes XMem memory operations as MCP tools.

Uses the XMem REST API (src/api) as its backend.
Configure XMEM_API_URL and (optionally) XMEM_API_KEY
in the environment or .env file.

Tools exposed:
    save_memory      — ingest a conversation turn into long-term memory
    search_memories  — semantic search across all memory domains
    retrieve_answer  — get an LLM-generated answer backed by stored memories
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP, Context

load_dotenv()

XMEM_API_URL = os.getenv("XMEM_API_URL", "http://localhost:8000")
XMEM_API_KEY = os.getenv("XMEM_API_KEY", "")
DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "mcp_user")


@dataclass
class XMemContext:
    """Shared context carrying the httpx client for the XMem API."""
    client: httpx.AsyncClient


@asynccontextmanager
async def xmem_lifespan(server: FastMCP) -> AsyncIterator[XMemContext]:
    headers = {"Content-Type": "application/json"}
    if XMEM_API_KEY:
        headers["Authorization"] = f"Bearer {XMEM_API_KEY}"

    async with httpx.AsyncClient(
        base_url=XMEM_API_URL, headers=headers, timeout=120,
    ) as client:
        resp = await client.get("/health")
        data = resp.json()
        if data.get("status") != "ready":
            print(f"[xmem-mcp] Warning: XMem API not ready — {data}")
        else:
            print("[xmem-mcp] Connected to XMem API.")
        yield XMemContext(client=client)

    print("[xmem-mcp] Shut down.")


mcp = FastMCP(
    "xmem-mcp",
    description="MCP server for long-term memory storage and retrieval with XMem",
    lifespan=xmem_lifespan,
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", "8050")),
)


def _client(ctx: Context) -> httpx.AsyncClient:
    return ctx.request_context.lifespan_context.client


@mcp.tool()
async def save_memory(
    ctx: Context,
    text: str,
    user_id: str = "",
    agent_response: str = "",
) -> str:
    """Save information to long-term memory.

    Stores the provided text through XMem's ingest pipeline which
    automatically classifies, extracts profiles, temporal events,
    and summaries.

    Args:
        ctx:  MCP server context
        text: The user message / information to memorize
        user_id: User identifier (defaults to server-configured default)
        agent_response: Optional assistant reply for richer summary extraction
    """
    client = _client(ctx)
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
    ctx: Context,
    query: str,
    user_id: str = "",
    top_k: int = 10,
    domains: str = "profile,temporal,summary",
) -> str:
    """Search stored memories using semantic similarity.

    Returns raw matching records from the specified memory domains
    without generating an LLM answer.

    Args:
        ctx:     MCP server context
        query:   Natural-language search query
        user_id: User identifier
        top_k:   Maximum results per domain
        domains: Comma-separated list of domains to search (profile, temporal, summary)
    """
    client = _client(ctx)
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
    ctx: Context,
    query: str,
    user_id: str = "",
    top_k: int = 5,
) -> str:
    """Answer a question using stored memories.

    Retrieves relevant memories and generates an LLM answer grounded
    in the user's stored knowledge.

    Args:
        ctx:     MCP server context
        query:   The question to answer
        user_id: User identifier
        top_k:   Number of source records to consider
    """
    client = _client(ctx)
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


async def main():
    transport = os.getenv("TRANSPORT", "sse")
    if transport == "sse":
        await mcp.run_sse_async()
    else:
        await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
