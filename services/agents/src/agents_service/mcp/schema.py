"""MCP (Model Context Protocol) server config: lets an agent call tools and
read resources exposed by external MCP servers mid-conversation, alongside
(or instead of) the simpler webhook-style tools in `actions/` — a plain
HTTP endpoint the platform calls vs. a whole MCP server the agent talks to.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents_service.core.partial import partial_model


class MCPServer(BaseModel):
    """One external MCP server the agent can call tools/resources on."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "server_id": "crm-mcp",
                "name": "CRM Tools",
                "url": "https://mcp.example.com/crm/mcp",
                "transport": "streamable_http",
                "auth_token": None,
                "enabled": True,
                "allowed_tools": ["lookup_customer", "create_ticket"],
            }
        }
    )

    server_id: str = Field(..., description="Unique identifier for this MCP server within the agent.")
    name: str = Field(..., description="Human-readable name shown in the agent builder UI.")
    url: str = Field(..., description="Endpoint of the MCP server.")
    transport: Literal["streamable_http", "sse"] = Field("streamable_http", description="MCP transport protocol used to talk to this server.")
    auth_token: str | None = Field(None, description="Bearer token/API key sent to this MCP server, if it requires one.")
    enabled: bool = Field(True, description="Whether this server's tools are available to the agent.")
    allowed_tools: list[str] = Field([], description="Tool names this agent may call on this server; empty allows every tool the server exposes.")


class MCPSettings(BaseModel):
    servers: list[MCPServer] = Field([], description="MCP servers available to this agent.")


MCPSettingsUpdate = partial_model(MCPSettings)
