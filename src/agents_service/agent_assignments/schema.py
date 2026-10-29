from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AssignmentCreate(BaseModel):
    """Body for POST /agents/{agent_id}/assignments."""

    model_config = ConfigDict(json_schema_extra={"example": {"user_id": "656f1a2b3c4d5e6f7a8b9c0d"}})

    user_id: str = Field(..., description="ID of the Developer user to grant access to this agent.")


class AssignmentOut(BaseModel):
    """One agent-to-user assignment record. Not currently returned directly
    by any endpoint (the assignment routes return a plain list of assignee
    user ids) — kept for future use and internal typing.
    """

    agent_id: str = Field(..., description="ID of the assigned agent.")
    user_id: str = Field(..., description="ID of the assigned user.")
    assigned_by: str = Field(..., description="ID of the user (an Admin) who created this assignment.")
    created_at: datetime = Field(..., description="When this assignment was created, in UTC.")
