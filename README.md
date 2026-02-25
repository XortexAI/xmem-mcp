<h1 align="center">XMem MCP: Long-Term Memory for AI Agents</h1>

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that gives any MCP-compatible AI agent persistent long-term memory powered by the XMem API.

The server connects to a running XMem API instance and exposes memory operations as MCP tools that agents in Cursor, Claude Desktop, Windsurf, n8n, and other clients can call directly.

## Architecture

```
MCP Client (Cursor / Claude Desktop / etc.)
    │
    │  MCP protocol (SSE or stdio)
    ▼
┌──────────────┐         HTTP / Bearer auth
│  xmem-mcp    │ ──────────────────────────► XMem API  (POST /v1/memory/*)
│  (this repo) │                             ├── /v1/memory/ingest
└──────────────┘                             ├── /v1/memory/search
                                             └── /v1/memory/retrieve
```

## Tools

The server exposes three tools:

| Tool | Description |
|------|-------------|
| **`save_memory`** | Ingest a conversation turn into long-term memory. XMem automatically classifies the input and extracts profile facts, temporal events, and summaries. |
| **`search_memories`** | Semantic search across memory domains (profile, temporal, summary). Returns raw matching records without an LLM answer. |
| **`retrieve_answer`** | Answer a question using stored memories. Retrieves relevant context and generates an LLM-grounded answer with source citations. |

## Prerequisites

- Python 3.11+
- A running XMem API instance (default: `http://localhost:8000`)

Start the XMem API first:

```bash
uvicorn src.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

## Installation

### Using uv

```bash
cd mcp
pip install uv
uv pip install -e .
```

### Using pip

```bash
cd mcp
pip install -e .
```

### Using Docker

```bash
docker build -t xmem-mcp --build-arg PORT=8050 .
```

## Configuration

Create a `.env` file in the `mcp/` directory (or set environment variables):

| Variable | Description | Default |
|----------|-------------|---------|
| `XMEM_API_URL` | Base URL of the XMem API | `http://localhost:8000` |
| `XMEM_API_KEY` | Bearer token for XMem API authentication | _(empty — no auth)_ |
| `DEFAULT_USER_ID` | Default user ID when none is provided by the caller | `mcp_user` |
| `TRANSPORT` | MCP transport protocol (`sse` or `stdio`) | `sse` |
| `HOST` | Host to bind to (SSE transport only) | `0.0.0.0` |
| `PORT` | Port to listen on (SSE transport only) | `8050` |

Example `.env`:

```env
XMEM_API_URL=http://localhost:8000
XMEM_API_KEY=your-api-key-here
DEFAULT_USER_ID=mcp_user
TRANSPORT=sse
HOST=0.0.0.0
PORT=8050
```

## Running the Server

### SSE Transport

```bash
# With uv
uv run src/main.py

# With Python directly
python src/main.py
```

### Docker (SSE)

```bash
docker run --env-file .env -p 8050:8050 xmem-mcp
```

## Integration with MCP Clients

### Cursor

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

### Windsurf

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

### Claude Desktop / Windsurf (stdio)

```json
{
  "mcpServers": {
    "xmem": {
      "command": "your/path/to/mcp/.venv/Scripts/python.exe",
      "args": ["your/path/to/mcp/src/main.py"],
      "env": {
        "TRANSPORT": "stdio",
        "XMEM_API_URL": "http://localhost:8000",
        "XMEM_API_KEY": "YOUR-API-KEY"
      }
    }
  }
}
```

### Docker (stdio)

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

> **Note for Docker users**: Use `host.docker.internal` instead of `localhost` when the XMem API is running on the host machine outside Docker.

Update the port in all examples above if you are using a value other than the default `8050`.
