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


DeepgramLanguages = [
    {"language": "English", "code": "en"},
    {"language": "Chinese", "code": "zh"},
    {"language": "Chinese (Mandarin)", "code": "zh-CN"},
    {"language": "Chinese (Taiwanese)", "code": "zh-TW"},
    {"language": "Danish", "code": "da"},
    {"language": "Dutch", "code": "nl"},
    {"language": "English", "code": "en"},
    {"language": "English (US)", "code": "en-US"},
    {"language": "English (Australia)", "code": "en-AU"},
    {"language": "English (UK)", "code": "en-GB"},
    {"language": "English (New Zealand)", "code": "en-NZ"},
    {"language": "English (India)", "code": "en-IN"},
    {"language": "French", "code": "fr"},
    {"language": "French (Canada)", "code": "fr-CA"},
    {"language": "German", "code": "de"},
    {"language": "Hindi", "code": "hi"},
    {"language": "Hindi (Latin)", "code": "hi-Latn"},
    {"language": "Portuguese", "code": "pt"},
    {"language": "Portuguese (Brazil)", "code": "pt-BR"},
    {"language": "Spanish", "code": "es"},
    {"language": "Spanish (Latin America)", "code": "es-419"},
    {"language": "Hindi", "code": "hi"},
    {"language": "Hindi (Latin)", "code": "hi-Latn"},
    {"language": "Italian", "code": "it"},
    {"language": "Japanese", "code": "ja"},
    {"language": "Korean", "code": "ko"},
    {"language": "Norwegian", "code": "no"},
    {"language": "Polish", "code": "pl"},
    {"language": "Portuguese", "code": "pt"},
    {"language": "Portuguese (Brazil)", "code": "pt-BR"},
    {"language": "Spanish (Latin America)", "code": "es-LATAM"},
    {"language": "Swedish", "code": "sv"},
    {"language": "Tamil", "code": "ta"},
    {"language": "Tamil (Latin)", "code": "taq"},
    {"language": "Ukrainian", "code": "uk"},
    {"language": "Turkish", "code": "tr"},
    {"language": "Swedish", "code": "sv"},
    {"language": "Indonesian", "code": "id"},
    {"language": "Portuguese", "code": "pt"},
    {"language": "Portuguese (Brazil)", "code": "pt-BR"},
    {"language": "Russian", "code": "ru"},
    {"language": "Thai", "code": "th"},
    {"language": "Multilingual", "code": "multi"},
]

STT_PROVIDERS: list[ProviderInfo] = [
    ProviderInfo(
        provider_id="deepgram",
        label="Deepgram",
        multilingual=True,
        models=[
            ModelInfo(
                model_id="nova-3",
                label="Nova-3",
                description="General-purpose real-time/streaming STT model.",
                supported_languages=DeepgramLanguages,
            ),
        ],
    )
]



TTS_PROVIDERS: list[ProviderInfo] = [
    ProviderInfo(
        provider_id="openai",
        label="OpenAI",
        multilingual=True,
        models=[
            ModelInfo(
                model_id="tts-1",
                label="GPT-4o TTS",
                description="Multilingual text-to-speech model.",
                voice_ids=["alloy", "ash", "ballad", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer"],
            ),
            ModelInfo(
                model_id="tts-1-hd",
                label="GPT-4o TTS HD",
                description="High-quality multilingual text-to-speech model.",
                voice_ids=["alloy", "ash", "ballad", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer"],
            ),
            ModelInfo(
                model_id="gpt-4o-mini-tts",
                label="GPT-4o TTS HD",
                description="High-quality multilingual text-to-speech model.",
                voice_ids=["alloy", "ash", "ballad", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer"],
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
                voice_ids=["en", "hi", "multi"],
            ),
        ],
    ),
]
