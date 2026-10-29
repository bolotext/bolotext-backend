"""Languages an agent can be configured with. The single source of truth for
both GET /languages (what the create-agent UI shows) and validation in
PUT /agents/{id}/languages. To support another language, add a row here.
"""

SUPPORTED_LANGUAGES: list[dict[str, str]] = [
    {"code": "hi-IN", "name": "Hindi"},
    {"code": "en-IN", "name": "English"},
    {"code": "kn-IN", "name": "Kannada"},
    {"code": "ta-IN", "name": "Tamil"},
    {"code": "te-IN", "name": "Telugu"},
    {"code": "ml-IN", "name": "Malayalam"},
    {"code": "bn-IN", "name": "Bengali"},
    {"code": "mr-IN", "name": "Marathi"},
    {"code": "pa-IN", "name": "Punjabi"},
]

SUPPORTED_LANGUAGE_CODES: frozenset[str] = frozenset(lang["code"] for lang in SUPPORTED_LANGUAGES)
