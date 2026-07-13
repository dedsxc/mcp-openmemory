"""
Main FastMCP server implementation for mem0 long-term memory.

This module wires MCP tools onto an existing mem0 REST server so an agent
can persist and recall memories across sessions.

Tools:
  * search_memory   -> recall memories relevant to a query
  * add_memory      -> store a message / fact
  * list_memories   -> list stored memories for a bucket
  * delete_memory   -> forget a single memory by id

Memory is isolated per ``user_id`` (a "bucket"). Callers may pass an explicit
user_id; otherwise MEM0_DEFAULT_USER_ID is used, giving the agent a single
shared long-term memory.
"""

from typing import Any

import httpx
from fastmcp import FastMCP

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


def _resolve_user_id(user_id: str | None) -> str:
    """Fall back to the default memory bucket when no user_id is given."""
    return user_id or config.default_user_id


@mcp.tool()
async def search_memory(
    query: str,
    user_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Search long-term memory for entries relevant to a query.

    Call this at the start of a task (or whenever prior context would help)
    to recall what was learned in earlier sessions.

    Args:
        query: Natural-language description of what to recall.
        user_id: Memory bucket to search. Defaults to the configured agent
            bucket when omitted.
        limit: Maximum number of memories to return (default from config).

    Returns:
        A list of memory objects, each with at least ``id`` and ``memory``
        (the remembered text) plus any relevance ``score`` mem0 provides.
    """
    payload = {
        "query": query,
        "filters": {"user_id": _resolve_user_id(user_id)},
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
    user_id: str | None = None,
    role: str = "user",
) -> dict[str, Any]:
    """
    Store a new memory (a fact, preference, or exchange) in long-term memory.

    Use this automatically when you learn something durable about the user or
    project, or on explicit request ("remember that ..."). mem0 runs a
    server-side extraction to decide what is worth keeping, so not every call
    creates a stored entry.

    Args:
        text: The content to remember.
        user_id: Memory bucket to write to. Defaults to the configured agent
            bucket when omitted.
        role: Message role to attribute the text to ("user" or "assistant").

    Returns:
        The mem0 response describing what, if anything, was stored.
    """
    payload = {
        "messages": [{"role": role, "content": text}],
        "user_id": _resolve_user_id(user_id),
    }
    async with httpx.AsyncClient(timeout=config.write_timeout) as client:
        response = await client.post(
            f"{config.base_url}/memories", headers=_headers(), json=payload
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def list_memories(
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    List all stored memories for a bucket.

    Args:
        user_id: Memory bucket to list. Defaults to the configured agent
            bucket when omitted.

    Returns:
        A list of memory objects with their ids and remembered text.
    """
    params = {"user_id": _resolve_user_id(user_id)}
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
    Start the OpenMemory MCP server in HTTP streamable mode.

    Server will be available at: http://{host}:{port}
    """
    import os

    print("🚀 Starting OpenMemory MCP server in HTTP mode...")
    print(
        f"📡 Server will be available at: "
        f"http://{config.server_host}:{config.server_port}"
    )
    print(f"🔗 mem0 instance: {config.base_url}")
    print()
    os.environ["MCP_HOST"] = config.server_host
    os.environ["MCP_PORT"] = str(config.server_port)
    mcp.run(
        transport="sse",
        host=config.server_host,
        port=config.server_port,
    )


if __name__ == "__main__":
    main()
