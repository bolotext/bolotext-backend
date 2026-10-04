from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.providers import service as provider_service
from agents_service.providers.schema import ProviderCatalog, ProviderInfo

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get(
    "",
    response_model=SuccessResponse[ProviderCatalog],
    summary="List all LLM/STT/TTS providers and models",
)
async def get_all_providers(auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Returns the full provider+model registry in one call — every LLM,
    STT (speech-to-text) and TTS (text-to-speech) provider available on this
    deployment, with the models each one offers. Use this to populate the
    agent builder's provider/model pickers for the `llm`, `transcriber`, and
    `voice-persona` sections. Read-only; there is no create/update endpoint
    for providers.

    **Auth:** bearer JWT required; any authenticated caller.

    **Errors:** none beyond authentication — `UNAUTHORIZED` if the bearer
    token is missing/invalid/expired.
    """
    return success_response(data=provider_service.get_catalog())


@router.get(
    "/llm",
    response_model=SuccessResponse[list[ProviderInfo]],
    summary="List LLM providers and models",
)
async def get_llm_providers(auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Returns just the LLM providers/models, for the agent builder's
    `llm.provider_id`/`llm.model_id` pickers.

    **Auth:** bearer JWT required; any authenticated caller.

    **Errors:** none beyond authentication — `UNAUTHORIZED` if the bearer
    token is missing/invalid/expired.
    """
    return success_response(data=provider_service.get_llm_providers())


@router.get(
    "/stt",
    response_model=SuccessResponse[list[ProviderInfo]],
    summary="List STT (speech-to-text) providers and models",
)
async def get_stt_providers(auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Returns just the STT providers/models, for the agent builder's
    `transcriber.provider_id`/`transcriber.model_id` pickers.

    **Auth:** bearer JWT required; any authenticated caller.

    **Errors:** none beyond authentication — `UNAUTHORIZED` if the bearer
    token is missing/invalid/expired.
    """
    return success_response(data=provider_service.get_stt_providers())


@router.get(
    "/tts",
    response_model=SuccessResponse[list[ProviderInfo]],
    summary="List TTS (text-to-speech) providers and voices",
)
async def get_tts_providers(auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Returns just the TTS providers/voices, for the agent builder's
    `voice_persona.provider_id`/`voice_persona.voice_id` pickers.

    **Auth:** bearer JWT required; any authenticated caller.

    **Errors:** none beyond authentication — `UNAUTHORIZED` if the bearer
    token is missing/invalid/expired.
    """
    return success_response(data=provider_service.get_tts_providers())
