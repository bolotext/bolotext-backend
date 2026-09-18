from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.providers import service as provider_service
from agents_service.providers.schema import ProviderCatalog, ProviderInfo

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("", response_model=SuccessResponse[ProviderCatalog])
async def get_all_providers(auth: AuthContext = Depends(get_current_auth)) -> dict:
    return success_response(data=provider_service.get_catalog())


@router.get("/llm", response_model=SuccessResponse[list[ProviderInfo]])
async def get_llm_providers(auth: AuthContext = Depends(get_current_auth)) -> dict:
    return success_response(data=provider_service.get_llm_providers())


@router.get("/stt", response_model=SuccessResponse[list[ProviderInfo]])
async def get_stt_providers(auth: AuthContext = Depends(get_current_auth)) -> dict:
    return success_response(data=provider_service.get_stt_providers())


@router.get("/tts", response_model=SuccessResponse[list[ProviderInfo]])
async def get_tts_providers(auth: AuthContext = Depends(get_current_auth)) -> dict:
    return success_response(data=provider_service.get_tts_providers())
