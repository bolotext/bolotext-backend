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
            ModelInfo(model_id="gpt-4o", label="GPT-4o", function_calling=True),
            ModelInfo(
                model_id="gpt-4o-mini",
                label="GPT-4o mini",
                description="Fast, low-cost general-purpose model.",
                function_calling=True
            ),
        ],
    )
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
        provider_id="deepgram",
        label="Deepgram",
        multilingual=True,
        models=[
            ModelInfo(
                model_id="nova-2",
                label="Nova-2",
                description="General-purpose real-time/streaming STT model.",
                supported_languages=["en", "hi"],
            ),
            ModelInfo(
                model_id="nova-3",
                label="Nova-3",
                description="General-purpose real-time/streaming STT model.",
                supported_languages=["en", "hi", "multi"],
            ),
        ],
    ),
    ProviderInfo(
        provider_id="sarvam",
        label="Sarvam AI",
        multilingual=True,
        models=[
            ModelInfo(
                model_id="saarika-v2",
                label="Saarika v2",
                description="Multilingual Indic-language STT model.",
                supported_languages=["en-IN", "hi-IN", "ta-IN", "te-IN", "kn-IN", "bn-IN", "mr-IN"],
            ),
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
        provider_id="deepgram",
        label="Deepgram",
        multilingual=True,
        models=[
            ModelInfo(
                model_id="aura-2",
                label="Aura-2",
                description="Real-time streaming TTS model.",
                supported_languages=["en", "hi", "multi"],
            ),
        ],
    ),
    ProviderInfo(
        provider_id="sarvam",
        label="Sarvam AI",
        multilingual=True,
        models=[
            ModelInfo(
                model_id="bulbul-v2",
                label="Bulbul v2",
                description="Multilingual Indic-language TTS model.",
                supported_languages=["en-IN", "hi-IN", "ta-IN", "te-IN", "kn-IN", "bn-IN", "mr-IN"],
            ),
        ],
    ),
]
