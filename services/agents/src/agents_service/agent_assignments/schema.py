from datetime import datetime

from pydantic import BaseModel


class AssignmentCreate(BaseModel):
    user_id: str


class AssignmentOut(BaseModel):
    agent_id: str
    user_id: str
    assigned_by: str
    created_at: datetime
