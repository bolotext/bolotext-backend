from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.prompt import service as prompt_service
from agents_service.prompt.schema import (
    AgentPromptUpdate,
    SystemPromptVersionOut,
    TestRenderRequest,
    TestRenderResponse,
)

router = APIRouter(prefix="/agents", tags=["agents:prompt"])


@router.patch("/{agent_id}/prompt", response_model=SuccessResponse[AgentOut])
async def update_prompt(
    agent_id: PydanticObjectId, payload: AgentPromptUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    agent, config = await agent_service.update_section(agent_id, auth, "prompt", payload.model_dump(exclude_unset=True))
    return success_response(message="Agent prompt updated", data=agent_service.to_out(agent, config))


@router.post("/{agent_id}/test", response_model=SuccessResponse[TestRenderResponse])
async def test_agent_prompt(
    agent_id: PydanticObjectId,
    payload: TestRenderRequest = TestRenderRequest(),
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    rendered = await agent_service.render_test(agent_id, auth, payload.sample_values)
    return success_response(data=TestRenderResponse(**rendered))


@router.get("/{agent_id}/prompt/versions", response_model=SuccessResponse[list[SystemPromptVersionOut]])
async def list_system_prompt_versions(
    agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    # Ownership check only — the versions themselves live in their own
    # collection (system_prompt_versions), not on AgentConfig.
    await agent_service.get_owned_agent(agent_id, auth)
    versions = await prompt_service.list_system_prompt_versions(agent_id)
    return success_response(
        data=[
            SystemPromptVersionOut(version=v.version, system_prompt=v.system_prompt, created_by=v.created_by, created_at=v.created_at)
            for v in versions
        ]
    )


@router.delete("/{agent_id}/prompt/versions/{version}", response_model=SuccessResponse[None])
async def delete_system_prompt_version(
    agent_id: PydanticObjectId, version: int, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    await agent_service.get_owned_agent(agent_id, auth)
    await prompt_service.delete_system_prompt_version(agent_id, version)
    return success_response(message="System prompt version deleted")
