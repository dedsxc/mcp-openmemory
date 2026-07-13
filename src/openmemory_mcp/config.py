"""
Configuration management for the OpenMemory MCP server.

Handles environment variables and settings validation.
"""

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Mem0Config(BaseSettings):
    """
    Configuration settings for connecting to the mem0 REST server.

    Attributes:
        mem0_url: Base URL of the mem0 REST server (e.g., http://mem0:8000)
        api_key: Admin API key, sent to mem0 as the ``X-API-Key`` header
        default_user_id: Memory bucket used when a caller does not pass one
        search_limit: Default number of memories returned by a search
        timeout: HTTP request timeout in seconds for reads (search/list)
        write_timeout: HTTP timeout for writes; ``add`` runs a server-side
            LLM extraction, so it needs a much longer budget than reads
        server_host: Host to bind the HTTP/SSE server to
        server_port: Port to bind the HTTP/SSE server to
    """

    model_config = SettingsConfigDict(
        env_prefix="MEM0_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mem0_url: HttpUrl = Field(
        default="http://mem0:8000",
        description="Base URL of the mem0 REST server",
    )

    api_key: str | None = Field(
        default=None,
        description="Admin API key sent to mem0 as the X-API-Key header",
    )

    default_user_id: str = Field(
        default="coder-agent",
        description="Memory bucket used when no identity header is present "
        "(stdio / local agent mode, or when require_identity is False)",
    )

    identity_header: str = Field(
        default="x-mem0-user-id",
        description="HTTP header carrying the end-user identity. Trusted: it "
        "must be injected by an authenticating layer (LibreChat, LiteLLM), "
        "never by the calling LLM. Compared case-insensitively.",
    )

    tenant_header: str = Field(
        default="x-mem0-tenant",
        description="HTTP header carrying the calling app/tenant. Prefixed to "
        "the user id to isolate apps sharing this server (e.g. librechat:alice). "
        "Optional; injected by the trusted layer. Compared case-insensitively.",
    )

    require_identity: bool = Field(
        default=True,
        description="When true, HTTP requests without an identity header are "
        "rejected (fail-closed). stdio requests always fall back to "
        "default_user_id since they carry no HTTP headers.",
    )

    search_limit: int = Field(
        default=5,
        description="Default number of memories returned by a search",
        ge=1,
        le=100,
    )

    timeout: int = Field(
        default=10,
        description="HTTP request timeout in seconds for reads",
        ge=1,
        le=300,
    )

    write_timeout: int = Field(
        default=60,
        description="HTTP request timeout in seconds for writes (add)",
        ge=1,
        le=600,
    )

    server_host: str = Field(
        default="0.0.0.0",
        description="Host to bind the HTTP/SSE server to",
    )

    server_port: int = Field(
        default=8000,
        description="Port to bind the HTTP/SSE server to",
        ge=1,
        le=65535,
    )

    @property
    def base_url(self) -> str:
        """Return the mem0 base URL as a string without a trailing slash."""
        return str(self.mem0_url).rstrip("/")
