"""
Configuration management for the OpenMemory MCP server.

Handles environment variables and settings validation.
"""

from typing import Annotated

from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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

    identity_headers: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description="Additional HTTP headers carrying the end-user identity, "
        "tried in order after ``identity_header``. Lets a single shared mem0 "
        "backend accept identities forwarded under different names by "
        "different authenticating layers (e.g. ``x-mem0-user-id`` for "
        "LibreChat/LiteLLM, ``x-coder-owner-id`` for Coder). The first header "
        "present with a non-empty value wins. Set via ``MEM0_IDENTITY_HEADERS`` "
        "as a comma-separated string (e.g. ``x-coder-owner-id``). All trusted: "
        "they must "
        "be injected by an authenticating layer, never by the calling LLM. "
        "Compared case-insensitively.",
    )

    @property
    def identity_header_candidates(self) -> list[str]:
        """Return the ordered, de-duplicated list of identity header names.

        ``identity_header`` (the primary/back-compatible name) is always tried
        first, followed by any extras in ``identity_headers``. Names are
        lower-cased for case-insensitive header lookup.
        """
        seen: set[str] = set()
        ordered: list[str] = []
        for name in [self.identity_header, *self.identity_headers]:
            key = (name or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                ordered.append(key)
        return ordered

    agent_header: str = Field(
        default="x-mem0-agent-id",
        description="HTTP header carrying the agent identity (e.g. koda, "
        "holmesgpt, librechat). Optional sub-scope within a user_id bucket, "
        "injected by the trusted layer. When absent, memories are scoped by "
        "user_id only (agent_id stays null). Compared case-insensitively.",
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

    @field_validator("identity_headers", mode="before")
    @classmethod
    def _split_identity_headers(cls, value: object) -> object:
        """Allow ``MEM0_IDENTITY_HEADERS`` as a comma-separated string.

        pydantic-settings otherwise expects a JSON list for ``list`` fields.
        A plain comma-separated value (``a,b,c``) is the friendlier form for
        an env var, so accept both. Empty entries are dropped.
        """
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value
