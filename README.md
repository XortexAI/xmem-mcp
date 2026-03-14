<div align="center">

# XMem MCP

**Long-term memory for AI agents.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-Compatible-34A853?style=flat-square)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-A259FF?style=flat-square)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)

A [Model Context Protocol](https://modelcontextprotocol.io) server that gives any MCP-compatible AI agent persistent long-term memory, powered by the XMem API. Connect it to Cursor, Claude Desktop, Windsurf, n8n, or any MCP client.

---

</div>

## See it in action

https://github.com/user-attachments/assets/60a1d5c3-2efe-4ef1-abb3-e334f5cc5fb7

---

## How it works

```
MCP Client (Cursor / Claude Desktop / Windsurf / n8n)
      |
      |  MCP protocol (SSE or stdio)
      v
  xmem-mcp            HTTP / Bearer auth
  (this repo)  ------------------------------>  XMem API
                                                  |-- POST /v1/memory/ingest
                                                  |-- POST /v1/memory/search
                                                  '-- POST /v1/memory/retrieve
```

Your AI agent calls XMem MCP tools like any other MCP tool. The server translates those calls into XMem API requests and returns structured results the agent can reason over.

---

## Tools

The server exposes three tools to the connected agent:

### $\color{#4285F4}{\textsf{save\_memory}}$

Ingest a conversation turn into long-term memory. XMem automatically classifies the input and extracts profile facts, temporal events, and summaries.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `text` | Yes | The user message or information to memorize |
| `user_id` | No | User identifier (falls back to `DEFAULT_USER_ID`) |
| `agent_response` | No | Assistant reply — enables richer summary extraction |

### $\color{#34A853}{\textsf{search\_memories}}$

Semantic search across memory domains. Returns raw matching records without generating an LLM answer.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `query` | Yes | -- | Natural-language search query |
| `user_id` | No | `DEFAULT_USER_ID` | User identifier |
| `top_k` | No | `10` | Max results per domain |
| `domains` | No | `profile,temporal,summary` | Comma-separated domains to search |

### $\color{#EA4335}{\textsf{retrieve\_answer}}$

Answer a question using stored memories. Retrieves relevant context and generates an LLM-grounded answer with source citations.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `query` | Yes | -- | The question to answer |
| `user_id` | No | `DEFAULT_USER_ID` | User identifier |
| `top_k` | No | `5` | Number of source records to consider |

---

## Getting started

### Prerequisites

- Python 3.11+
- A running XMem API instance (default: `http://localhost:8000`)

Start the XMem API first:

```bash
uvicorn src.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

### Install

**uv (recommended)**

```bash
pip install uv
uv pip install -e .
```

**pip**

```bash
pip install -e .
```

**Docker**

```bash
docker build -t xmem-mcp --build-arg PORT=8050 .
```

### Run

**SSE transport (default)**

```bash
uv run src/main.py
# or
python src/main.py
```

**Docker**

```bash
docker run --env-file .env -p 8050:8050 xmem-mcp
```

---

## Configuration

Create a `.env` file in the project root (or set environment variables):

| Variable | Default | Description |
|----------|---------|-------------|
| `XMEM_API_URL` | `http://localhost:8000` | Base URL of the XMem API |
| `XMEM_API_KEY` | _(empty)_ | Bearer token for XMem API authentication |
| `DEFAULT_USER_ID` | `mcp_user` | Default user ID when none is provided by the caller |
| `TRANSPORT` | `sse` | MCP transport protocol (`sse` or `stdio`) |
| `HOST` | `0.0.0.0` | Bind address (SSE transport only) |
| `PORT` | `8050` | Listen port (SSE transport only) |

Example `.env`:

```env
XMEM_API_URL=http://localhost:8000
XMEM_API_KEY=your-api-key-here
DEFAULT_USER_ID=mcp_user
TRANSPORT=sse
HOST=0.0.0.0
PORT=8050
```

---

## Client integration

### $\color{#4285F4}{\textsf{Cursor}}$

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "xmem": {
      "transport": "sse",
      "url": "http://localhost:8050/sse"
    }
  }
}
```

### $\color{#34A853}{\textsf{Windsurf (SSE)}}$

```json
{
  "mcpServers": {
    "xmem": {
      "transport": "sse",
      "serverUrl": "http://localhost:8050/sse"
    }
  }
}
```

### $\color{#A259FF}{\textsf{Claude Desktop / Windsurf (stdio)}}$

```json
{
  "mcpServers": {
    "xmem": {
      "command": "your/path/to/xmem-mcp/.venv/Scripts/python.exe",
      "args": ["your/path/to/xmem-mcp/src/main.py"],
      "env": {
        "TRANSPORT": "stdio",
        "XMEM_API_URL": "http://localhost:8000",
        "XMEM_API_KEY": "YOUR-API-KEY"
      }
    }
  }
}
```

### $\color{#EA4335}{\textsf{Docker (stdio)}}$

```json
{
  "mcpServers": {
    "xmem": {
      "command": "docker",
      "args": ["run", "--rm", "-i",
               "-e", "TRANSPORT",
               "-e", "XMEM_API_URL",
               "-e", "XMEM_API_KEY",
               "xmem-mcp"],
      "env": {
        "TRANSPORT": "stdio",
        "XMEM_API_URL": "http://host.docker.internal:8000",
        "XMEM_API_KEY": "YOUR-API-KEY"
      }
    }
  }
}
```

> **Docker users**: Use `host.docker.internal` instead of `localhost` when the XMem API runs on the host machine outside Docker.

Update the port in all examples if you changed it from the default `8050`.

---

## Architecture

```
xmem-mcp/
  src/
    main.py       MCP server — tool definitions, HTTP client, transport setup
    utils.py      Helpers — user ID derivation, env readers
  .env.example    Environment variable template
  Dockerfile      Container build
  pyproject.toml  Project metadata and dependencies
```

### Key internals

- **Async throughout** — `httpx.AsyncClient` with 120s timeout for all XMem API calls
- **Bearer auth** — Automatically attaches `Authorization` header when `XMEM_API_KEY` is set
- **Dual transport** — SSE for HTTP-based clients, stdio for local process execution
- **Error handling** — HTTP and runtime errors return user-friendly messages (truncated to 200 chars)
- **Domain-aware** — Three memory domains (`profile`, `temporal`, `summary`) with per-domain confidence scoring

---

<div align="center">

Built by [Xortex](https://github.com/xortex-ai)

</div>
