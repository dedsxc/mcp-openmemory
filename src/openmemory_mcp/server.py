"""
Main FastMCP server implementation for mem0 long-term memory.

This module wires MCP tools onto an existing mem0 REST server so an agent
can persist and recall memories across sessions.

Tools:
  * search_memory   -> recall memories relevant to a query
  * add_memory      -> store a message / fact
  * list_memories   -> list stored memories for a bucket
  * delete_memory   -> forget a single memory by id

Memory is isolated per ``user_id`` (a "bucket"). The bucket is NEVER chosen by
the calling LLM: it is derived server-side from trusted HTTP headers injected
by an authenticating layer (LibreChat, LiteLLM). This prevents one app/user
from reading another's memories by simply passing a different user_id.

Resolution (see ``_resolve_user_id``):
  * HTTP transport: ``<tenant>:<user>`` from the ``x-mem0-tenant`` /
    ``x-mem0-user-id`` headers. Missing identity -> rejected (fail-closed)
    when ``require_identity`` is true.
  * stdio transport (local agent, no HTTP headers): falls back to
    ``default_user_id``.
"""

from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers

from .config import Mem0Config

# Initialize configuration
config = Mem0Config()

# Create FastMCP server instance
mcp = FastMCP("OpenMemory (mem0)")


def _headers() -> dict[str, str]:
    """Build request headers, including the mem0 admin key when configured."""
    headers = {"content-type": "application/json"}
    if config.api_key:
        headers["X-API-Key"] = config.api_key
    return headers


def _resolve_user_id() -> str:
    """Derive the memory bucket from trusted request context.

    The bucket is taken from HTTP headers set by an authenticating layer and
    is intentionally NOT a tool argument, so the calling LLM cannot target an
    arbitrary user's memory.

    * Over HTTP: ``<tenant>:<user>`` (tenant optional). If no identity header
      is present and ``require_identity`` is true, the call is rejected.
    * Without an HTTP request (stdio / local agent): falls back to
      ``default_user_id``.

    Raises:
        ToolError: when identity is required but absent.
    """
    # include_all=True so custom x-mem0-* headers are not stripped.
    http_headers = get_http_headers(include_all=True)

    # No HTTP context at all -> stdio/local agent mode.
    if not http_headers:
        return config.default_user_id

    user = (http_headers.get(config.identity_header.lower()) or "").strip()
    tenant = (http_headers.get(config.tenant_header.lower()) or "").strip()

    if not user:
        if config.require_identity:
            raise ToolError(
                "Missing identity: this memory server requires the "
                f"'{config.identity_header}' header, injected by the "
                "authenticating layer. Refusing to access memory without a "
                "verified user."
            )
        return config.default_user_id

    return f"{tenant}:{user}" if tenant else user


@mcp.tool()
async def search_memory(
    query: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Search long-term memory for entries relevant to a query.

    Call this at the start of a task (or whenever prior context would help)
    to recall what was learned in earlier sessions.

    The memory bucket is determined automatically from your authenticated
    identity; you cannot and need not specify whose memory to read.

    Args:
        query: Natural-language description of what to recall.
        limit: Maximum number of memories to return (default from config).

    Returns:
        A list of memory objects, each with at least ``id`` and ``memory``
        (the remembered text) plus any relevance ``score`` mem0 provides.
    """
    payload = {
        "query": query,
        "filters": {"user_id": _resolve_user_id()},
        "limit": limit or config.search_limit,
    }
    async with httpx.AsyncClient(timeout=config.timeout) as client:
        response = await client.post(
            f"{config.base_url}/search", headers=_headers(), json=payload
        )
        response.raise_for_status()
        data = response.json()
    return data.get("results", data if isinstance(data, list) else [])


@mcp.tool()
async def add_memory(
    text: str,
    role: str = "user",
) -> dict[str, Any]:
    """
    Store a new memory (a fact, preference, or exchange) in long-term memory.

    Use this automatically when you learn something durable about the user or
    project, or on explicit request ("remember that ..."). mem0 runs a
    server-side extraction to decide what is worth keeping, so not every call
    creates a stored entry.

    The memory bucket is determined automatically from your authenticated
    identity; you cannot and need not specify whose memory to write.

    Args:
        text: The content to remember.
        role: Message role to attribute the text to ("user" or "assistant").

    Returns:
        The mem0 response describing what, if anything, was stored.
    """
    payload = {
        "messages": [{"role": role, "content": text}],
        "user_id": _resolve_user_id(),
    }
    async with httpx.AsyncClient(timeout=config.write_timeout) as client:
        response = await client.post(
            f"{config.base_url}/memories", headers=_headers(), json=payload
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def list_memories() -> list[dict[str, Any]]:
    """
    List all stored memories for your authenticated identity's bucket.

    Returns:
        A list of memory objects with their ids and remembered text.
    """
    params = {"user_id": _resolve_user_id()}
    async with httpx.AsyncClient(timeout=config.timeout) as client:
        response = await client.get(
            f"{config.base_url}/memories", headers=_headers(), params=params
        )
        response.raise_for_status()
        data = response.json()
    return data.get("results", data if isinstance(data, list) else [])


@mcp.tool()
async def delete_memory(
    memory_id: str,
) -> dict[str, Any]:
    """
    Delete a single memory by its id.

    Note: mem0 deletes by id without a user filter, so ids should only be
    obtained from this identity's own ``search_memory`` / ``list_memories``
    results (both scoped to the caller's bucket).

    Args:
        memory_id: The id of the memory to forget (from search/list results).

    Returns:
        A status object confirming the deletion.
    """
    async with httpx.AsyncClient(timeout=config.timeout) as client:
        response = await client.delete(
            f"{config.base_url}/memories/{memory_id}", headers=_headers()
        )
        response.raise_for_status()
        try:
            return response.json()
        except Exception:
            return {"status": "deleted", "id": memory_id}


def main():
    """
    Entry point for the OpenMemory MCP server.

    Runs in stdio mode (for MCP clients like Claude Desktop).
    """
    mcp.run()


def serve_sse():
    """
    Start the OpenMemory MCP server in SSE (Server-Sent Events) mode.

    Server will be available at: http://{host}:{port}/sse
    """
    print("🚀 Starting OpenMemory MCP server in SSE mode...")
    print(
        f"📡 Server will be available at: "
        f"http://{config.server_host}:{config.server_port}/sse"
    )
    print(f"🔗 mem0 instance: {config.base_url}")
    print()
    mcp.run(
        transport="sse",
        host=config.server_host,
        port=config.server_port,
    )


def serve_http():
    """
    Start the OpenMemory MCP server in streamable-HTTP mode.

    This is the modern MCP transport (supersedes SSE). The server exposes a
    single endpoint at http://{host}:{port}/mcp/ that clients connect to.
    """
    print("🚀 Starting OpenMemory MCP server in streamable-HTTP mode...")
    print(
        f"📡 Server will be available at: "
        f"http://{config.server_host}:{config.server_port}/mcp/"
    )
    print(f"🔗 mem0 instance: {config.base_url}")
    print()
    mcp.run(
        transport="http",
        host=config.server_host,
        port=config.server_port,
    )


if __name__ == "__main__":
    main()
