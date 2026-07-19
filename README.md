# mcp-openmemory

A [FastMCP](https://github.com/jlowin/fastmcp) server that exposes
[mem0](https://github.com/mem0ai/mem0) long-term memory to MCP clients (e.g. an
AI coding agent) over SSE.

It is a thin, stateless MCP layer over an **existing** mem0 REST server
(`http://mem0:8000`) — it does **not** run its own vector store. This keeps a
single source of truth for memory (the mem0 pgvector store) instead of
introducing a second, disconnected memory silo.

## Tools

| Tool | Purpose |
| --- | --- |
| `search_memory(query, user_id?, limit?)` | Recall memories relevant to a query. Call at the start of a task. |
| `add_memory(text, user_id?, role?)` | Store a fact/preference/exchange. Use automatically when you learn something durable, or on explicit request. |
| `list_memories(user_id?)` | List stored memories for a bucket. |
| `delete_memory(memory_id)` | Forget a single memory by id. |

Memory is isolated per `user_id` ("bucket"). When a caller omits `user_id`,
`MEM0_DEFAULT_USER_ID` is used, giving the agent a single shared memory.

## Configuration

Environment variables (prefix `MEM0_`):

| Variable | Default | Description |
| --- | --- | --- |
| `MEM0_MEM0_URL` | `http://mem0:8000` | Base URL of the mem0 REST server |
| `MEM0_API_KEY` | _(none)_ | Admin API key, sent as `X-API-Key` |
| `MEM0_DEFAULT_USER_ID` | `coder-agent` | Bucket used when no `user_id` is passed |
| `MEM0_IDENTITY_HEADER` | `x-mem0-user-id` | Primary trusted header carrying the end-user identity |
| `MEM0_IDENTITY_HEADERS` | _(none)_ | Extra identity headers, tried after `MEM0_IDENTITY_HEADER` (comma-separated, e.g. `x-coder-owner-id`). First non-empty wins. |
| `MEM0_SEARCH_LIMIT` | `5` | Default number of memories per search |
| `MEM0_TIMEOUT` | `10` | HTTP timeout (s) for reads (search/list) |
| `MEM0_WRITE_TIMEOUT` | `60` | HTTP timeout (s) for writes (add runs a server-side LLM extraction) |
| `MEM0_SERVER_HOST` | `0.0.0.0` | Bind host for the SSE server |
| `MEM0_SERVER_PORT` | `8000` | Bind port for the SSE server |

## Run

```bash
pip install -e .
openmemory-mcp-sse   # SSE at http://0.0.0.0:8000/sse
# or
openmemory-mcp       # stdio mode
```

## Container

Built by the `release-containers` workflow (release-please) to
`ghcr.io/dedsxc/openmemory-mcp:<version>` for `linux/amd64,linux/arm64`.
