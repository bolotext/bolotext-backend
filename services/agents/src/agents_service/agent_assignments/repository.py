from beanie import PydanticObjectId

from agents_service.agent_assignments.model import AgentAssignment


async def create(agent_id: PydanticObjectId, user_id: str, org_id: str | None, assigned_by: str) -> AgentAssignment:
    assignment = AgentAssignment(agent_id=agent_id, user_id=user_id, org_id=org_id, assigned_by=assigned_by)
    await assignment.insert()
    return assignment


async def is_assigned(agent_id: PydanticObjectId, user_id: str) -> bool:
    return (
        await AgentAssignment.find_one(AgentAssignment.agent_id == agent_id, AgentAssignment.user_id == user_id)
        is not None
    )


async def get(agent_id: PydanticObjectId, user_id: str) -> AgentAssignment | None:
    return await AgentAssignment.find_one(AgentAssignment.agent_id == agent_id, AgentAssignment.user_id == user_id)


async def list_for_agent(agent_id: PydanticObjectId) -> list[AgentAssignment]:
    return await AgentAssignment.find(AgentAssignment.agent_id == agent_id).to_list()


async def list_agent_ids_for_user(user_id: str, org_id: str | None) -> list[PydanticObjectId]:
    assignments = await AgentAssignment.find(
        AgentAssignment.user_id == user_id, AgentAssignment.org_id == org_id
    ).to_list()
    return [a.agent_id for a in assignments]


async def delete(assignment: AgentAssignment) -> None:
    await assignment.delete()


async def delete_all_by_agent_id(agent_id: PydanticObjectId) -> None:
    """Called when the agent itself is deleted — see agents.service.delete_agent."""
    await AgentAssignment.find(AgentAssignment.agent_id == agent_id).delete()
