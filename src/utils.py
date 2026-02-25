"""
Utility helpers for the XMem MCP server.
"""

from __future__ import annotations

import hashlib
import os


def default_user_id(raw: str = "user") -> str:
    """Derive a deterministic user ID from a plain string."""
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def get_xmem_api_url() -> str:
    return os.getenv("XMEM_API_URL", "http://localhost:8000")


def get_xmem_api_key() -> str:
    return os.getenv("XMEM_API_KEY", "")
