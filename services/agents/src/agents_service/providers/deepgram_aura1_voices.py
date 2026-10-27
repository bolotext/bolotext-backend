"""Deepgram Aura (v1) English TTS voices, from https://developers.deepgram.com/docs/tts-models.md
(the "Aura 1: All Available English Voices" table). Each voice is model string `aura-{voice}-en`.
"""

from agents_service.providers.schema import VoiceOption

# (language code, language name, [(voice name, gender, accent)])
_AURA1_CATALOG: list[tuple[str, str, list[tuple[str, str, str | None]]]] = [
    ("en", "English", [
        ("Asteria", "female", "American"),
        ("Luna", "female", "American"),
        ("Stella", "female", "American"),
        ("Athena", "female", "British"),
        ("Hera", "female", "American"),
        ("Orion", "male", "American"),
        ("Arcas", "male", "American"),
        ("Perseus", "male", "American"),
        ("Angus", "male", "Irish"),
        ("Orpheus", "male", "American"),
        ("Helios", "male", "British"),
        ("Zeus", "male", "American"),
    ]),
]

DEEPGRAM_AURA1_VOICES: list[VoiceOption] = [
    VoiceOption(voice_id=f"aura-{name.lower()}-{code}", label=name, gender=gender, language=language, accent=accent)
    for code, language, voices in _AURA1_CATALOG
    for name, gender, accent in voices
]

assert len({v.voice_id for v in DEEPGRAM_AURA1_VOICES}) == len(DEEPGRAM_AURA1_VOICES), "duplicate voice id"
