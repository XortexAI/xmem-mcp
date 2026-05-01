"""
XMem MCP Server — exposes XMem memory + scanner + code operations as MCP tools.

Uses the XMem REST API (src/api) as its backend.
Configure XMEM_API_URL and (optionally) XMEM_API_KEY
in the environment or .env file.

Environment variables:
    XMEM_API_URL     — Backend API URL (default: http://localhost:8000)
    XMEM_API_KEY     — Optional API key for authentication
    TRANSPORT        — Transport mode: "streamable-http" (default), "sse", or "stdio"
    HOST             — Server host (default: 0.0.0.0)
    PORT             — Server port (default: 8050)
    MCP_PATH         — HTTP endpoint path for streamable-http (default: /mcp)

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

import json
import os
import contextvars
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from scanner_tools import register_scanner_tools

load_dotenv()

XMEM_API_URL = os.getenv("XMEM_API_URL", "http://localhost:8000")

# ═══════════════════════════════════════════════════════════════════════════
# Configuration Persistence for OAuth
# ═══════════════════════════════════════════════════════════════════════════
CONFIG_DIR = Path.home() / ".xmem"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _load_stored_config() -> dict:
    """Load stored config including cached API key from OAuth."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_config(config: dict) -> None:
    """Save config to disk for persistence across restarts."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def _get_api_key() -> str | None:
    """
    Get API key from environment or stored config.
    Priority: 1) Environment variable, 2) Stored config file
    """
    # Priority 1: Environment variable (from MCP config)
    if env_key := os.getenv("XMEM_API_KEY"):
        return env_key

    # Priority 2: Stored config (from previous OAuth)
    config = _load_stored_config()
    if cached_key := config.get("api_key"):
        return cached_key

    return None


# Initialize global API key (may be None if not configured yet)
XMEM_API_KEY: str | None = _get_api_key()

# Context variable to store the current request's API key (for OAuth passthrough)
mcp_api_key = contextvars.ContextVar("mcp_api_key", default="")

class ContextAuth(httpx.Auth):
    """Dynamically injects the API key from the current request context."""
    def auth_flow(self, request: httpx.Request):
        key = mcp_api_key.get() or XMEM_API_KEY
        if key:
            request.headers["Authorization"] = f"Bearer {key}"
        yield request

_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Get the global HTTP client, creating it if needed."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            base_url=XMEM_API_URL, 
            timeout=120,
            auth=ContextAuth()
        )
    return _http_client


def _check_auth() -> str | None:
    """
    Check if API key is configured.
    Returns error message if not authenticated, None if authenticated.
    """
    if not (XMEM_API_KEY or mcp_api_key.get()):
        return (
            "⚠️ XMem API key not configured.\n\n"
            "Option 1 - Environment variable (recommended for local setup):\n"
            "  Add to your MCP config:\n"
            '  "env": {"XMEM_API_KEY": "your-api-key"}\n\n'
            "Option 2 - OAuth (for ChatGPT, Claude UI, etc.):\n"
            "  1. Visit https://xmem.in/auth/mcp to generate a token\n"
            '  2. Call: authenticate(token="xm-temp-xxxxx")'
        )
    return None


async def _close_client() -> None:
    """Close the global HTTP client gracefully."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


@asynccontextmanager
async def _app_lifespan() -> AsyncIterator[None]:
    """Manage application lifespan - cleanup on shutdown."""
    try:
        yield
    finally:
        await _close_client()


# Get config from environment for consistent defaults
_HOST = os.getenv("HOST", "0.0.0.0")
_PORT = int(os.getenv("PORT", "8050"))

mcp = FastMCP(
    "xmem-mcp",
    description=(
        "MCP server for long-term memory storage, retrieval, "
        "and code intelligence with XMem. Provides memory tools "
        "(save, search, retrieve) and native code retrieval tools "
        "(search_symbols, impact_analysis, read_file_code, etc)."
    ),
    host=_HOST,
    port=_PORT,
)


# ═══════════════════════════════════════════════════════════════════════════
# Memory Tools (existing)
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
async def save_memory(
    text: str,
    agent_response: str = "",
) -> str:
    """Save information to long-term memory.

    Stores the provided text through XMem's ingest pipeline which
    automatically classifies, extracts profiles, temporal events,
    and summaries.

    Args:
        text: The user message / information to memorize
        agent_response: Optional assistant reply for richer summary extraction
    """
    # Check authentication
    if auth_error := _check_auth():
        return auth_error

    client = _get_client()

    try:
        resp = await client.post("/v1/memory/ingest", json={
            "user_query": text,
            "agent_response": agent_response,
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
                conf = d.get("confidence") or 0
                parts.append(
                    f"  {domain}: {len(ops)} ops, "
                    f"confidence={conf:.1%}"
                )

        return "\n".join(parts)

    except httpx.HTTPStatusError as exc:
        return f"API error ({exc.response.status_code}): {exc.response.text[:200]}"
    except httpx.RequestError as exc:
        return f"Network error connecting to XMem API: {exc}"
    except httpx.TimeoutException as exc:
        return f"Request timed out after 120s: {exc}"


@mcp.tool()
async def search_memories(
    query: str,
    top_k: int = 10,
    domains: str = "profile,temporal,summary",
) -> str:
    """Search stored memories using semantic similarity.

    Returns raw matching records from the specified memory domains
    without generating an LLM answer.

    Args:
        query:   Natural-language search query
        top_k:   Maximum results per domain
        domains: Comma-separated list of domains to search (profile, temporal, summary)
    """
    # Check authentication
    if auth_error := _check_auth():
        return auth_error

    client = _get_client()
    domain_list = [d.strip() for d in domains.split(",") if d.strip()]

    try:
        resp = await client.post("/v1/memory/search", json={
            "query": query,
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
    except httpx.RequestError as exc:
        return f"Network error connecting to XMem API: {exc}"
    except httpx.TimeoutException as exc:
        return f"Request timed out after 120s: {exc}"


@mcp.tool()
async def retrieve_answer(
    query: str,
    top_k: int = 5,
) -> str:
    """Answer a question using stored memories.

    Retrieves relevant memories and generates an LLM answer grounded
    in the user's stored knowledge.

    Args:
        query:   The question to answer
        top_k:   Number of source records to consider
    """
    # Check authentication
    if auth_error := _check_auth():
        return auth_error

    client = _get_client()

    try:
        resp = await client.post("/v1/memory/retrieve", json={
            "query": query,
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
    except httpx.RequestError as exc:
        return f"Network error connecting to XMem API: {exc}"
    except httpx.TimeoutException as exc:
        return f"Request timed out after 120s: {exc}"


@mcp.tool()
async def authenticate(token: str) -> str:
    """
    Exchange temporary OAuth token for a permanent API key.

    Use this when connecting from ChatGPT, Claude UI, or other clients
    where you cannot set environment variables.

    Steps:
    1. Visit https://xmem.in/auth/mcp while logged into your account
    2. Copy the temporary token (expires in 10 minutes)
    3. Call this tool with the token

    The API key will be cached to ~/.xmem/config.json for future sessions.

    Args:
        token: Temporary token from https://xmem.in/auth/mcp
    """
    global XMEM_API_KEY, _http_client

    # Create fresh client without auth for this exchange
    client = httpx.AsyncClient(base_url=XMEM_API_URL, timeout=30)

    try:
        resp = await client.post(
            "/v1/auth/mcp-exchange",
            json={"temp_token": token, "client_type": "mcp"}
        )

        if resp.status_code == 401:
            return (
                "❌ Invalid or expired token.\n\n"
                "The token may have expired (valid for 10 minutes).\n"
                "Please visit https://xmem.in/auth/mcp to generate a new token."
            )

        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == "error":
            return f"❌ Authentication failed: {data.get('error', 'Unknown error')}"

        new_api_key = data.get("api_key")
        user_info = data.get("user", {})

        if not new_api_key:
            return "❌ Authentication failed: No API key received from server"

        # Store for persistence
        config = {
            "api_key": new_api_key,
            "user_id": user_info.get("id"),
            "email": user_info.get("email"),
            "cached_at": datetime.now().isoformat(),
        }
        _save_config(config)

        # Update global API key
        XMEM_API_KEY = new_api_key

        # Reset HTTP client to use new API key
        if _http_client is not None:
            await _http_client.aclose()
            _http_client = None

        return (
            f"✅ Authentication successful!\n"
            f"User: {user_info.get('email', user_info.get('id', 'Unknown'))}\n"
            f"API key cached to ~/.xmem/config.json\n\n"
            f"You can now use all XMem memory tools."
        )

    except httpx.RequestError as exc:
        return f"❌ Network error connecting to XMem API: {exc}"
    except httpx.TimeoutException:
        return "❌ Request timed out. Please try again."
    except Exception as exc:
        return f"❌ Unexpected error during authentication: {exc}"
    finally:
        await client.aclose()


# ═══════════════════════════════════════════════════════════════════════════
# Code Intelligence Tools
# ═══════════════════════════════════════════════════════════════════════════
register_scanner_tools(mcp, _get_client, _check_auth)

# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════

async def run_custom_http_server(app_factory, transport_name: str, **kwargs):
    """Run the server with custom auth middleware for HTTP transports."""
    import uvicorn
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    
    class AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header[len("Bearer "):]
                mcp_api_key.set(token)
            return await call_next(request)

    # Get the Starlette app from FastMCP
    app = app_factory(**kwargs)
    app.add_middleware(AuthMiddleware)

    config = uvicorn.Config(
        app,
        host=_HOST,
        port=_PORT,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()

async def main_async():
    """Async entry point to handle uvicorn lifecycle."""
    transport = os.getenv("TRANSPORT", "streamable-http").lower()
    
    if transport == "streamable-http":
        path = os.getenv("MCP_PATH", "/mcp")
        await run_custom_http_server(mcp.streamable_http_app, "streamable-http", path=path)
    elif transport == "sse":
        await run_custom_http_server(mcp.sse_app, "sse")
    else:
        # stdio is synchronous in FastMCP
        mcp.run(transport="stdio")

def main():
    import asyncio
    transport = os.getenv("TRANSPORT", "streamable-http").lower()
    if transport in ("sse", "streamable-http"):
        asyncio.run(main_async())
    else:
        mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
