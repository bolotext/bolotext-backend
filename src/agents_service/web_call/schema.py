from typing import Literal

from pydantic import BaseModel, Field

Environment = Literal["development", "stage", "production"]


class WebCallTokenRequest(BaseModel):
    """Authenticated (builder) web call. The caller picks which environment's
    config the voice agent loads."""

    environment: Environment = Field("development", description="Which environment's config the agent loads for this call.")
    time_zone: str = Field("Asia/Kolkata", description="Caller's IANA time zone.")
    custom_variables: dict[str, str] = Field(
        default_factory=dict,
        description="Extra key/value data forwarded to the agent in the participant metadata.",
    )


class PublicWebCallTokenRequest(BaseModel):
    """Public (embedded widget) web call. Always runs the agent's production config."""

    parent_origin: str | None = Field(None, description="Origin of the site embedding the widget; must be in the agent's allowed origins.")
    time_zone: str = Field("Asia/Kolkata", description="Caller's IANA time zone.")
    custom_variables: dict[str, str] = Field(default_factory=dict, description="Extra key/value data forwarded to the agent.")


class WebCallToken(BaseModel):
    server_url: str = Field(description="LiveKit server websocket URL to connect to.")
    participant_token: str = Field(description="Short-lived LiveKit access token.")
    room_name: str
    agent_id: str
    environment: Environment
