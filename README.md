<div align="center">

# XMem MCP

**Long-term memory + code intelligence for AI agents.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-Compatible-34A853?style=flat-square)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-A259FF?style=flat-square)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)

A [Model Context Protocol](https://modelcontextprotocol.io) server that gives any MCP-compatible AI agent persistent long-term memory **and** code intelligence, powered by the XMem API. Connect it to Cursor, Claude Desktop, Windsurf, ChatGPT, n8n, or any MCP client.

---

</div>

## How it works

```
MCP Client (Cursor / Claude Desktop / Windsurf / ChatGPT / n8n)
      |
      |  MCP protocol (SSE or stdio)
      v
  xmem-mcp            HTTP / Bearer auth
  (this repo)  -------------------------------->  XMem API
                                                    |-- POST /v1/memory/ingest
                                                    |-- POST /v1/memory/search
                                                    |-- POST /v1/memory/retrieve
                                                    |-- GET  /v1/code/*
                                                    '-- POST /v1/code/query
```

---

## Tools

### Memory Tools

| Tool | Description |
|------|-------------|
| `save_memory` | Ingest a conversation turn into long-term memory |
| `search_memories` | Semantic search across memory domains |
| `retrieve_answer` | LLM-generated answer backed by stored memories |

### Code Intelligence Tools (Native)

These tools run directly against the Neo4j CodeStore to allow the MCP Client to autonomously navigate the codebase.

| Tool | Description |
|------|-------------|
| `search_symbols` | Hybrid search across functions, classes, and methods |
| `search_files` | Search for files by their semantic summary |
| `search_annotations` | Search team annotations, bug reports, and design decisions |
| `impact_analysis` | Graph traversal showing callers, callees, and inheritance |
| `get_file_context` | Get the structural context of a file (defined symbols and imports) |
| `read_symbol_code` | Read the EXACT raw source code of a specific function or class |
| `read_file_code` | Read the ENTIRE raw source code of a specific file |
| `search_snippets` | Search the user's personal saved code snippets |
| `get_repo_structure` | Get a list of all directories in the repository |
| `get_directory_summary` | Get the semantic summary of a directory |
| `get_file_summary` | Get the semantic summary of a file |
| `list_indexed_repos` | List all repositories scanned by you |
| `browse_community_catalog` | Browse publicly shared code indexes |

---

## Getting started

### Prerequisites

- Python 3.11+
- A running XMem API instance (default: `http://localhost:8000`)

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

### Run

**SSE transport (default)**

```bash
uv run src/main.py
# or
python src/main.py
```

---

## Configuration

Create a `.env` file in the project root:

| Variable | Default | Description |
|----------|---------|-------------|
| `XMEM_API_URL` | `http://localhost:8000` | Base URL of the XMem API |
| `XMEM_API_KEY` | _(empty)_ | Bearer token for XMem API authentication |
| `DEFAULT_USER_ID` | `mcp_user` | Default user ID when none is provided |
| `TRANSPORT` | `sse` | MCP transport protocol (`sse` or `stdio`) |
| `HOST` | `0.0.0.0` | Bind address (SSE transport only) |
| `PORT` | `8050` | Listen port (SSE transport only) |

---

## Client integration

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

### Claude Desktop / Windsurf (stdio)

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

---

## Architecture

```
xmem-mcp/
  src/
    main.py            MCP server — memory tools, transport setup
    scanner_tools.py   Code intelligence tool definitions
    utils.py           Helpers — user ID derivation, env readers
  .env.example         Environment variable template
  Dockerfile           Container build
  pyproject.toml       Project metadata and dependencies
```

---

<div align="center">

Built by [Xortex](https://github.com/xortex-ai)

</div>
