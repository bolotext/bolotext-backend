from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Scopes an API token can carry. A token only works on the routes that
# explicitly accept its scope (see the Agents service's /agents/config).
AGENT_CONFIG_READ = "agent-config:read"
CALL_LOG_WRITE = "call-log:write"


class ApiTokenCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"name": "voice-agent-production"}})

    name: str = Field(min_length=1, max_length=100, description="A label to recognise this token by, e.g. the service that uses it.")


class ApiTokenOut(BaseModel):
    id: str = Field(description="The token's id (use it to revoke).")
    name: str = Field(description="The label given at creation.")
    token_prefix: str = Field(description="The first characters of the token, to tell tokens apart. Never enough to use it.")
    scopes: list[str] = Field(description="What the token may do, e.g. `agent-config:read`, `call-log:write`.")
    created_by: str = Field(description="Id of the Super Admin who created it.")
    created_at: datetime = Field(description="When it was created (UTC).")
    revoked: bool = Field(description="Whether it has been revoked and no longer works.")
    revoked_at: datetime | None = Field(None, description="When it was revoked (UTC).")


class ApiTokenCreated(ApiTokenOut):
    token: str = Field(description="The full token. Shown only in this response; it cannot be retrieved again.")
