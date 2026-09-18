"""MCP (Model Context Protocol) server config: lets an agent call tools and
read resources exposed by external MCP servers mid-conversation, alongside
(or instead of) the simpler webhook-style tools in `actions/` — a plain
HTTP endpoint the platform calls vs. a whole MCP server the agent talks to.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from agents_service.core.partial import partial_model


class MCPServer(BaseModel):
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

    server_id: str
    name: str
    url: str
    transport: Literal["streamable_http", "sse"] = "streamable_http"
    auth_token: str | None = None  # bearer token/API key the platform sends to this MCP server, if required
    enabled: bool = True
    allowed_tools: list[str] = []  # empty = allow every tool this server exposes


class MCPSettings(BaseModel):
    servers: list[MCPServer] = []


MCPSettingsUpdate = partial_model(MCPSettings)
