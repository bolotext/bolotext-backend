"""Deepgram Aura-2 TTS voices, from https://developers.deepgram.com/docs/tts-models.md
(the "All Available" tables). Each voice is model string `aura-2-{voice}-{language}`.
"""

from agents_service.providers.schema import VoiceOption

# (language code, language name, [(voice name, gender, accent)])
_AURA2_CATALOG: list[tuple[str, str, list[tuple[str, str, str | None]]]] = [
    ("en", "English", [
        ("Amalthea", "female", "Filipino"),
        ("Andromeda", "female", "American"),
        ("Apollo", "male", "American"),
        ("Arcas", "male", "American"),
        ("Aries", "male", "American"),
        ("Asteria", "female", "American"),
        ("Athena", "female", "American"),
        ("Atlas", "male", "American"),
        ("Aurora", "female", "American"),
        ("Callista", "female", "American"),
        ("Cora", "female", "American"),
        ("Cordelia", "female", "American"),
        ("Delia", "female", "American"),
        ("Draco", "male", "British"),
        ("Electra", "female", "American"),
        ("Harmonia", "female", "American"),
        ("Helena", "female", "American"),
        ("Hera", "female", "American"),
        ("Hermes", "male", "American"),
        ("Hyperion", "male", "Australian"),
        ("Iris", "female", "American"),
        ("Janus", "female", "American"),
        ("Juno", "female", "American"),
        ("Jupiter", "male", "American"),
        ("Luna", "female", "American"),
        ("Mars", "male", "American"),
        ("Minerva", "female", "American"),
        ("Neptune", "male", "American"),
        ("Odysseus", "male", "American"),
        ("Ophelia", "female", "American"),
        ("Orion", "male", "American"),
        ("Orpheus", "male", "American"),
        ("Pandora", "female", "British"),
        ("Phoebe", "female", "American"),
        ("Pluto", "male", "American"),
        ("Saturn", "male", "American"),
        ("Selene", "female", "American"),
        ("Thalia", "female", "American"),
        ("Theia", "female", "Australian"),
        ("Vesta", "female", "American"),
        ("Zeus", "male", "American"),
    ]),
    ("es", "Spanish", [
        ("Sirio", "male", "Mexican"),
        ("Nestor", "male", "Peninsular"),
        ("Carina", "female", "Peninsular"),
        ("Celeste", "female", "Colombian"),
        ("Alvaro", "male", "Peninsular"),
        ("Diana", "female", "Peninsular"),
        ("Aquila", "male", "Latin American"),
        ("Selena", "female", "Latin American"),
        ("Estrella", "female", "Mexican"),
        ("Javier", "male", "Mexican"),
        ("Agustina", "female", "Peninsular"),
        ("Antonia", "female", "Argentine"),
        ("Gloria", "female", "Colombian"),
        ("Luciano", "male", "Mexican"),
        ("Olivia", "female", "Mexican"),
        ("Silvia", "female", "Peninsular"),
        ("Valerio", "male", "Mexican"),
    ]),
    ("nl", "Dutch", [
        ("Beatrix", "female", "Dutch"),
        ("Daphne", "female", "Dutch"),
        ("Cornelia", "female", "Dutch"),
        ("Sander", "male", "Dutch"),
        ("Hestia", "female", "Dutch"),
        ("Lars", "male", "Dutch"),
        ("Roman", "male", "Dutch"),
        ("Rhea", "female", "Dutch"),
        ("Leda", "female", "Dutch"),
    ]),
    ("fr", "French", [
        ("Agathe", "female", "French"),
        ("Hector", "male", "French"),
    ]),
    ("de", "German", [
        ("Elara", "female", "German"),
        ("Aurelia", "female", "German"),
        ("Lara", "female", "German"),
        ("Julius", "male", "German"),
        ("Fabian", "male", "German"),
        ("Kara", "female", "German"),
        ("Viktoria", "female", "German"),
    ]),
    ("it", "Italian", [
        ("Melia", "female", "Italian"),
        ("Elio", "male", "Italian"),
        ("Flavio", "male", "Italian"),
        ("Maia", "female", "Italian"),
        ("Cinzia", "female", "Italian"),
        ("Cesare", "male", "Italian"),
        ("Livia", "female", "Italian"),
        ("Dionisio", "male", "Italian"),
        ("Demetra", "female", "Italian"),
    ]),
    ("ja", "Japanese", [
        ("Uzume", "female", "Japanese"),
        ("Ebisu", "male", "Japanese"),
        ("Fujin", "male", "Japanese"),
        ("Izanami", "female", "Japanese"),
        ("Ama", "female", "Japanese"),
    ]),
]

DEEPGRAM_AURA2_VOICES: list[VoiceOption] = [
    VoiceOption(voice_id=f"aura-2-{name.lower()}-{code}", label=name, gender=gender, language=language, accent=accent)
    for code, language, voices in _AURA2_CATALOG
    for name, gender, accent in voices
]

assert len({v.voice_id for v in DEEPGRAM_AURA2_VOICES}) == len(DEEPGRAM_AURA2_VOICES), "duplicate voice id"
