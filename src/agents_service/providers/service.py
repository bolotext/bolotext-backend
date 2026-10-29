import time

from agents_service.core.config import get_settings
from agents_service.providers.schema import ProviderCatalog, ProviderInfo
from agents_service.providers.seed_data import LLM_PROVIDERS, STT_PROVIDERS, TTS_PROVIDERS

_cache: dict[str, tuple[float, list[ProviderInfo]]] = {}


def _cached(kind: str, seed: list[ProviderInfo]) -> list[ProviderInfo]:
    ttl = get_settings().provider_cache_ttl_seconds
    now = time.monotonic()
    entry = _cache.get(kind)
    if entry is not None and now - entry[0] < ttl:
        return entry[1]

    _cache[kind] = (now, seed)
    return seed


def get_llm_providers() -> list[ProviderInfo]:
    return _cached("llm", LLM_PROVIDERS)


def get_stt_providers() -> list[ProviderInfo]:
    return _cached("stt", STT_PROVIDERS)


def get_tts_providers() -> list[ProviderInfo]:
    return _cached("tts", TTS_PROVIDERS)


def get_catalog() -> ProviderCatalog:
    return ProviderCatalog(llm=get_llm_providers(), stt=get_stt_providers(), tts=get_tts_providers())
