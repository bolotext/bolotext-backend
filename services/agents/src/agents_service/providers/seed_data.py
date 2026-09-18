"""Provider/model registry seed data. This is intentionally plain code, not a
Mongo collection: it's read-only, small, and changes only on deploy — see
providers/service.py for the in-process cache in front of it.
"""

from agents_service.providers.schema import ModelInfo, ProviderInfo

LLM_PROVIDERS: list[ProviderInfo] = [
    ProviderInfo(
        provider_id="openai",
        label="OpenAI",
        supports_function_calling=True,
        multilingual=True,
        models=[
            ModelInfo(model_id="gpt-4o", label="GPT-4o", function_calling=True, supported_languages=["en", "hi"]),
            ModelInfo(
                model_id="gpt-4o-mini",
                label="GPT-4o mini",
                description="Fast, low-cost general-purpose model.",
                function_calling=True,
                supported_languages=["en", "hi"],
            ),
        ],
    ),
    ProviderInfo(
        provider_id="groq",
        label="Groq",
        supports_function_calling=True,
        multilingual=False,
        models=[
            ModelInfo(
                model_id="llama-3.3-70b-versatile",
                label="Llama 3.3 70B (Versatile)",
                function_calling=True,
                supported_languages=["en"],
            ),
        ],
    ),
    ProviderInfo(
        provider_id="gnani",
        label="Gnani SLM",
        supports_function_calling=True,
        multilingual=True,
        models=[
            ModelInfo(
                model_id="gnani-slm-v1",
                label="Gnani SLM v1",
                description="In-house small language model tuned for Indian-language voice conversations.",
                function_calling=True,
                supported_languages=["en-IN", "hi-IN", "ta-IN", "te-IN", "kn-IN", "bn-IN", "mr-IN"],
            ),
        ],
    ),
]

STT_PROVIDERS: list[ProviderInfo] = [
    ProviderInfo(
        provider_id="gnani",
        label="Gnani ASR",
        multilingual=True,
        models=[
            ModelInfo(
                model_id="gnani-stt-v2",
                label="Gnani ASR v2",
                supported_languages=["en-IN", "hi-IN", "ta-IN", "te-IN", "kn-IN", "bn-IN", "mr-IN"],
            ),
        ],
    ),
    ProviderInfo(
        provider_id="elevenlabs",
        label="ElevenLabs",
        multilingual=True,
        models=[ModelInfo(model_id="scribe-v1", label="Scribe v1", supported_languages=["en"])],
    ),
    ProviderInfo(
        provider_id="microsoft",
        label="Microsoft Azure Speech",
        multilingual=True,
        models=[
            ModelInfo(model_id="azure-stt-standard", label="Azure STT (Standard)", supported_languages=["en", "hi"])
        ],
    ),
]

TTS_PROVIDERS: list[ProviderInfo] = [
    ProviderInfo(
        provider_id="gnani",
        label="Gnani TTS",
        multilingual=True,
        models=[
            ModelInfo(
                model_id="gnani-tts-v2",
                label="Gnani TTS v2",
                supported_languages=["en-IN", "hi-IN", "ta-IN", "te-IN", "kn-IN", "bn-IN", "mr-IN"],
            ),
        ],
    ),
    ProviderInfo(
        provider_id="elevenlabs",
        label="ElevenLabs",
        multilingual=True,
        models=[ModelInfo(model_id="eleven_multilingual_v2", label="Eleven Multilingual v2", supported_languages=["en", "hi"])],
    ),
]
