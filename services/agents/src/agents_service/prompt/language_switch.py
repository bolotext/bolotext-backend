"""Hardcoded, language-aware templates behind AgentPrompt.language_switch_mode.

`implicit` and `explicit` each render a prompt for a language-switch/
identification LLM call from a fixed template, trimmed to just the languages
the agent is actually configured for (AgentConfig.languages) — an agent set
to Hindi + English only never sees Kannada/Tamil/Telugu STT lines, phrases,
or examples in its rendered prompt. `custom` bypasses the template entirely;
the caller uses AgentPrompt.language_switch_prompt verbatim instead (see
prompt.service.validate_language_switch for the save-time rule this implies).

Only five languages have hardcoded template content today (Hindi, English,
Kannada, Tamil, Telugu); anything else in AgentConfig.languages is ignored
for this template's purposes. Rendering is a no-op (returns None) below two
selected languages — there is nothing to switch between.
"""

from dataclasses import dataclass
from typing import Literal

Mode = Literal["implicit", "explicit", "custom"]

# Canonical order the original hand-written templates used; every generated
# block (language list, phrases, examples) follows it.
_ORDER = ["Hindi", "English", "Kannada", "Tamil", "Telugu"]

# AgentConfig.languages holds locale-ish codes (see agent_details/schema.py,
# e.g. "hi-IN"). Bare names are accepted too, case-insensitively, so a
# frontend can pass either. Anything not listed here is irrelevant to this
# template and silently ignored.
_CODE_ALIASES: dict[str, str] = {
    "hi": "Hindi", "hi-in": "Hindi", "hindi": "Hindi",
    "en": "English", "en-in": "English", "english": "English",
    "kn": "Kannada", "kn-in": "Kannada", "kannada": "Kannada",
    "ta": "Tamil", "ta-in": "Tamil", "tamil": "Tamil",
    "te": "Telugu", "te-in": "Telugu", "telugu": "Telugu",
}


def resolve_selected_languages(languages: list[str]) -> list[str]:
    """AgentConfig.languages -> the subset of _ORDER it refers to, in
    canonical order. An agent with `["hi-IN", "en-IN"]` resolves to
    `["Hindi", "English"]`; unrecognized codes (any language beyond the five
    above) are dropped rather than erroring — this template simply doesn't
    cover them yet.
    """
    found = {_CODE_ALIASES[code.strip().lower()] for code in languages if code.strip().lower() in _CODE_ALIASES}
    return [name for name in _ORDER if name in found]


@dataclass(frozen=True)
class _LanguageSpec:
    direct_phrases: list[str]  # native + English phrasings of "switch to this language"
    colloquial_words: list[str]  # bare single-word triggers, e.g. "hindi", "हिंदी"
    # Two natural, non-switch sentences proving fluency in this language —
    # used verbatim by `implicit` (expected output = this language) and
    # `explicit` (expected output = "None": neither sentence asks to switch).
    identify_examples: list[dict[str, str]]
    # One explicit switch request, phonetically attempted by every STT engine
    # — `explicit`-only (expected output = this language).
    switch_example: dict[str, str]


_LANGUAGES: dict[str, _LanguageSpec] = {
    "Hindi": _LanguageSpec(
        direct_phrases=[
            "मुझे हिंदी में बात करनी है", "हिंदी में बात करो", "Hindi mein baat karo",
            "Switch to Hindi", "Speak in Hindi", "Talk in Hindi",
            "Please continue in Hindi", "Let's switch to Hindi", "Hindi",
        ],
        colloquial_words=["hindi", "हिंदी"],
        identify_examples=[
            {
                "Hindi": "मैं घर जा रहा हूं", "English": "main ghar ja raha hoon",
                "Kannada": "ಮೈ ಘರ್ ಜಾ ರಹಾ ಹೂ", "Tamil": "மைன் கர் ஜா ரஹா ஹூன்", "Telugu": "మైన్ ఘర్ జా రహా హూన్",
            },
            {
                "Hindi": "क्या हाल है", "English": "kya haal hai",
                "Kannada": "ಕ್ಯಾ ಹಾಲ್ ಹೈ", "Tamil": "க்யா ஹால் ஹை", "Telugu": "క్యా హాల్ హై",
            },
        ],
        switch_example={
            "Hindi": "मुझे हिंदी में बात करनी है", "English": "mujhe hindi mein baat karni hai",
            "Kannada": "ಮುಜೆ ಹಿಂದಿ ಮೈ ಬಾತ್ ಕರ್ನಿ ಹೈ", "Tamil": "முஜே ஹிந்தி மைன் பாத் கர்னி ஹை", "Telugu": "ముజే హిందీ మైన్ బాత్ కర్ని హై",
        },
    ),
    "English": _LanguageSpec(
        direct_phrases=[
            "I want to speak in English", "I want to talk in English", "Can you speak in english",
            "Switch to english", "Speak in English", "Talk in English",
            "Please continue in English", "Let's switch to English", "English",
        ],
        colloquial_words=["english", "angrezi"],
        identify_examples=[
            {
                "Hindi": "माय लैपटॉप इज़ नॉट वर्किंग", "English": "my laptop is not working",
                "Kannada": "ಮೈ ಲ್ಯಾಪ್‌ಟಾಪ್ ಈಸ್ ನಾಟ್ ವರ್ಕಿಂಗ್", "Tamil": "மை லேப்டாப் இஸ் நாட் வொர்க்கிங்", "Telugu": "మై ల్యాప్‌టాప్ ఈజ్ నాట్ వర్కింగ్",
            },
            {
                "Hindi": "प्लीज़ हेल्प मी", "English": "please help me",
                "Kannada": "ಪ್ಲೀಸ್ ಹೆಲ್ಪ್ ಮಿ", "Tamil": "ப்ளீஸ் ஹெல்ப் மீ", "Telugu": "ప్లీజ్ హెల్ప్ మీ",
            },
        ],
        switch_example={
            "Hindi": "आई वांट टू स्पीक इन इंग्लिश", "English": "I want to speak in English",
            "Kannada": "ಐ ವಾಂಟ್ ಟು ಸ್ಪೀಕ್ ಇನ್ ಇಂಗ್ಲಿಷ್", "Tamil": "ஐ வாண்ட் டு ஸ்பீக் இன் இங்கிலீஷ்", "Telugu": "ఐ వాంట్ టు స్పీక్ ఇన్ ఇంగ్లీష్",
        },
    ),
    "Kannada": _LanguageSpec(
        direct_phrases=[
            "ನಾನು ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡಬೇಕು", "Kannadadalli matadi", "Kannadadalli mathadibeku",
            "Switch to Kannada", "Speak in Kannada", "Talk in Kannada",
            "Please continue in Kannada", "Let's switch to Kannada", "Kannada",
        ],
        colloquial_words=["kannada", "ಕನ್ನಡ"],
        identify_examples=[
            {
                "Hindi": "नानु मनेगे होगुत्त‍िदेने", "English": "naanu manege hōgutiddene",
                "Kannada": "ನಾನು ಮನೆಗೆ ಹೋಗುತ್ತಿದ್ದೇನೆ", "Tamil": "நான் மனேக ஹொகுத்துத்திறேன்", "Telugu": "నాను మనెగే హోగుత్తుందెనె",
            },
            {
                "Hindi": "हेगिद्दीरी", "English": "hēgiddīri",
                "Kannada": "ಹೇಗಿದ್ದೀರಿ", "Tamil": "ஹேகித்திரி", "Telugu": "ఏగెద్దిరి",
            },
        ],
        switch_example={
            "Hindi": "नानु कन्नड‍‍अल्लीं मंताद‍‍बेकू", "English": "nānu kannaḍadalli māṭādabekū",
            "Kannada": "ನಾನು ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡಬೇಕು", "Tamil": "நான் கன்னடத்துல மடாடபேகு", "Telugu": "నాను కన్నడదల్లి మాటలాడబేకు",
        },
    ),
    "Tamil": _LanguageSpec(
        direct_phrases=[
            "நான் தமிழில் பேச வேண்டும்", "Tamilil pesungal",
            "Switch to Tamil", "Speak in Tamil", "Talk in Tamil",
            "Please continue in Tamil", "Let's switch to Tamil", "Tamil",
        ],
        colloquial_words=["tamil", "தமிழ்"],
        identify_examples=[
            {
                "Hindi": "नां वीट्टुकु पोगिरेँ", "English": "naan veettu-kku po-girein",
                "Kannada": "ನಾನ್ ವಿಟ್ಟಕ್ಕು ಪೋಗಿರೇನ್", "Tamil": "நான் வீட்டுக்கு போகிறேன்", "Telugu": "నాన్ వీట్టుక్కు పోకేరెన్",
            },
            {
                "Hindi": "एप्पडी इरुक्कींग्‌", "English": "eppadi irukkeenga",
                "Kannada": "ಎப்படி ಇருத்தீங்க", "Tamil": "எப்படி இருக்கீங்க", "Telugu": "ఎప్படి ఇరుక్కీంగ",
            },
        ],
        switch_example={
            "Hindi": "नां తமிழிल् पेस वेण्‍डुम्", "English": "Naan Tamilil peesa vendum.",
            "Kannada": "ನಾನ್ ತಮಿಳ್ಲಿನ್ ಬೇಸ ವೇಣುಮ್", "Tamil": "நான் தமிழில் பேச வேண்டும்", "Telugu": "నాన్ తమిళిఁ పేస వేఁడెం",
        },
    ),
    "Telugu": _LanguageSpec(
        direct_phrases=[
            "నేను తెలుగులో మాట్లాడాలి", "Telugu lo matladandi", "Telugu lo matladu",
            "Switch to Telugu", "Speak in Telugu", "Talk in Telugu",
            "Please continue in Telugu", "Let's switch to Telugu", "Telugu",
        ],
        colloquial_words=["telugu", "తెలుగు"],
        identify_examples=[
            {
                "Hindi": "नेनु ఇంటికి वेल्तून्नानु", "English": "nēnu iṇṭiki veḷṭunnānu",
                "Kannada": "ನೇನು ಇಂಟಿಕಿ ವೆಲ್ಲುತ್ತಾನನು", "Tamil": "நெனு இண்டிக்కி வெளுத்துன்னானு", "Telugu": "నేను ఇంటికి వెళ్తున్నాను",
            },
            {
                "Hindi": "एला आरूं", "English": "elaa unnaaru",
                "Kannada": "ಎಲಾಂ ಉಂಟುರಾ", "Tamil": "எலா உண்ணுரு", "Telugu": "ఎలా ఉన్నారు",
            },
        ],
        switch_example={
            "Hindi": "नेनु तेलुगुलो म्पाड़ाली", "English": "nēnu telugu lō māṭlādāli",
            "Kannada": "ನೇನು ತೆಲುಗುಲೋ ಮಾಟಾಡಾಲಿ", "Tamil": "நேன் தெலுங்கிலோ மடாடாளி", "Telugu": "నేను తెలుగులో మాట్లాడాలి",
        },
    ),
}

# Shared by both modes: single words / numbers / dates / interjections that
# must never trigger or be misread as a language switch, regardless of mode.
_NEUTRAL_EXAMPLES: list[dict[str, str]] = [
    {"Hindi": "राहुल शर्मा", "English": "rahul sharma", "Kannada": "ರಾಹುಲ್ ಶರ್ಮಾ", "Tamil": "ராகுல் சர்மா", "Telugu": "రాహుల్ శర్మ"},
    {"Hindi": "मुंबई", "English": "mumbai", "Kannada": "ಮುಂಬೈ", "Tamil": "மும்பை", "Telugu": "ముంబై"},
    {"Hindi": "सैमसंग", "English": "samsung", "Kannada": "ಸ್ಯಾಮ್‌ಸಂಗ್", "Tamil": "சாம்சங்", "Telugu": "శామ్‌సంగ్"},
    {"Hindi": "१५ अगस्त २०२४", "English": "15th august 2024", "Kannada": "15 ಆಗಸ್ಟ್ 2024", "Tamil": "15 ஆகஸ்ட் 2024", "Telugu": "15 ఆగస్టు 2024"},
    {"Hindi": "५ पी एम", "English": "5 p m", "Kannada": "5 ಪಿ ಎಂ", "Tamil": "5 பி எம்", "Telugu": "5 పి ఎం"},
    {"Hindi": "९८७६५४३२१०", "English": "9876543210", "Kannada": "9876543210", "Tamil": "9876543210", "Telugu": "9876543210"},
    {"Hindi": "५०० रुपीस", "English": "500 rupees", "Kannada": "500 ರೂಪಾಯಿ", "Tamil": "500 ரூபாய்", "Telugu": "500 రూపాయలు"},
    {"Hindi": "१० किलोग्राम", "English": "10 kilograms", "Kannada": "10 ಕಿಲೋಗ್ರಾಂ", "Tamil": "10 கிலோகிராம்", "Telugu": "10 కిలోగ్రాములు"},
    {"Hindi": "वेनस्डे", "English": "wednesday", "Kannada": "ವೆಡ್ನೆಸ್ಡೇ", "Tamil": "புதன்", "Telugu": "బుధవారం"},
    {"Hindi": "नवंबर", "English": "november", "Kannada": "ನವೆಂಬರ್", "Tamil": "நவம்பர்", "Telugu": "నవంబర్"},
    {"Hindi": "आर बी आई", "English": "r b i", "Kannada": "ಆರ್ ಬಿ ಐ", "Tamil": "ஆர் பி ஐ", "Telugu": "ఆర్ బి ఐ"},
    {"Hindi": "हेलो", "English": "hello", "Kannada": "ಹಲೋ", "Tamil": "ஹலோ", "Telugu": "హలో"},
    {"Hindi": "ओके", "English": "okay", "Kannada": "ಓಕೆ", "Tamil": "ஓகே", "Telugu": "ఓకే"},
    {"Hindi": "नो", "English": "no", "Kannada": "ನೋ", "Tamil": "நோ", "Telugu": "నో"},
    {"Hindi": "मैडम", "English": "madam", "Kannada": "ಮೇಡಂ", "Tamil": "மேடம்", "Telugu": "మేడం"},
    {"Hindi": "हम्म", "English": "hmm", "Kannada": "ಹ್ಮ್", "Tamil": "ஹ்ம்ம்", "Telugu": "హ్మ్మ్"},
    {"Hindi": "सेविंग्स अकाउंट", "English": "savings account", "Kannada": "ಸೇವಿಂಗ್ಸ್ ಅಕೌಂಟ್", "Tamil": "சேவிங்ஸ் அக்கவுண்ட்", "Telugu": "సేవింగ్స్ ఖాతా"},
    {"Hindi": "कंप्यूटर", "English": "computer", "Kannada": "ಕಂಪ್ಯೂಟರ್", "Tamil": "கம்ப்யூட்டர்", "Telugu": "కంప్యూటర్"},
    {"Hindi": "ब्लॉक ए", "English": "block a", "Kannada": "ಬ್ಲಾಕ್ ಎ", "Tamil": "பிளாக் ஏ", "Telugu": "బ్లాక్ ఎ"},
    {"Hindi": "टेबल", "English": "table", "Kannada": "ಟೇಬಲ್", "Tamil": "டேபிள்", "Telugu": "టేబుల్"},
]


def _join(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _filter_row(row: dict[str, str], selected: list[str]) -> dict[str, str]:
    return {lang: row[lang] for lang in selected if lang in row}


def _format_example(n: int, row: dict[str, str], selected: list[str], output: str) -> str:
    lines = "\n".join(f"         - {lang} STT: {text}" for lang, text in _filter_row(row, selected).items())
    return f"    Example {n}:\n      * Input:\n{lines}\n      * Output:\n         - {output}"


def _input_format_block(selected: list[str]) -> str:
    return "\n".join(f"      - {lang} STT: [{lang} ASR output]" for lang in selected)


def _output_values_block(selected: list[str]) -> str:
    return "\n".join(f'         - "{lang}"' for lang in selected) + '\n         - "None"'


def _direct_phrases_block(selected: list[str]) -> str:
    blocks = []
    for lang in selected:
        phrase_lines = "\n".join(f'                     - "{p}"' for p in _LANGUAGES[lang].direct_phrases)
        blocks.append(f"                  - {lang}:\n{phrase_lines}")
    return "\n".join(blocks)


def _colloquial_block(selected: list[str]) -> str:
    lines = []
    for lang in selected:
        for word in _LANGUAGES[lang].colloquial_words:
            lines.append(f'                  - "{word}" ⇒ Output: {lang}')
    return "\n".join(lines)


def _shared_sections(selected: list[str]) -> dict[str, str]:
    return {
        "languages_joined": _join(selected),
        "input_format": _input_format_block(selected),
        "direct_phrases": _direct_phrases_block(selected),
        "colloquial": _colloquial_block(selected),
    }


def render_explicit_prompt(selected: list[str]) -> str:
    s = _shared_sections(selected)
    examples = []
    n = 1
    for row in _NEUTRAL_EXAMPLES:
        examples.append(_format_example(n, row, selected, "None"))
        n += 1
    for lang in selected:
        for row in _LANGUAGES[lang].identify_examples:
            examples.append(_format_example(n, row, selected, "None"))
            n += 1
    for lang in selected:
        examples.append(_format_example(n, _LANGUAGES[lang].switch_example, selected, lang))
        n += 1
    examples_block = "\n\n".join(examples)

    return f"""# Language Switch Detection Agent for {s['languages_joined']} STT

## Role:
   * You are a specialized language switch detection agent that analyzes outputs from {s['languages_joined']} STT engines.
   * Your sole purpose is to detect when users explicitly request to switch/speak/talk in a specific language.
   * You do NOT perform general language detection for regular conversation.

## Objective:
   * Given transcripts from {s['languages_joined']} STT engines,
   * Detect ONLY explicit language switch requests where the user clearly states they want to speak/talk/continue in a specific language.
   * **Return the target language ONLY if explicitly requested by the user.**
   * **For all other cases (including natural conversation), return "None".**

## Instructions:
   * Input Format:
{s['input_format']}

   * Output Format:
      - Output only one of the following values (case-sensitive):
{_output_values_block(selected)}

## Analysis Process:
    * Language Detection Rules:
        * Primary Rule - Explicit Language Declaration:
            * **CRITICAL RULE**: When a language switch request is detected, IGNORE the previously detected language from conversation history and ONLY return the NEW target language being requested. The switch command overrides all previous language context.

            * Direct Phrases Indicating Intent:
               - If a transcript (STT output) contains an explicit statement of language preference—such as:
{s['direct_phrases']}
               - Output: matching the declared preference

            * Colloquial Language Words:
               - If the transcript contains common alternate terms:
{s['colloquial']}
               - These should be detected as explicit language intents and mapped accordingly.

            * Priority:
               - The output must reflect the NEW target language, not the previously detected language.
               - If any form of explicit language declaration (as above) appears ANYWHERE in the transcript, that must take precedence—override all other language inference logic.

   * Decision Logic:
      - **ONLY** return a language name if the user explicitly requests to speak/talk/continue/switch to that language.
      - If no explicit language request is detected → Output: "None"
      - Regular conversation in any language (without explicit language switching intent) → Output: "None"
      - Language name mentioned in context but not as a switch request → Output: "None"

## Sample Examples:

{examples_block}

## IMPORTANT:
   - Output must contain ONLY one of: {", ".join(f'"{lang}"' for lang in selected)}, or "None"
   - Do NOT explain or add extra text — just return the final decision
   - **CRITICAL**: Return a language name ONLY when the user explicitly requests to speak/talk/continue/switch to that language
   - For ALL other cases (regular conversation, questions, statements) — return "None"
   - Language switch requests contain phrases like "speak in", "talk in", "switch to", "I want to speak in", etc.
   - If no explicit language switching intent is detected, always return "None"
"""


def render_implicit_prompt(selected: list[str]) -> str:
    s = _shared_sections(selected)
    examples = []
    n = 1
    for row in _NEUTRAL_EXAMPLES:
        examples.append(_format_example(n, row, selected, "None"))
        n += 1
    for lang in selected:
        for row in _LANGUAGES[lang].identify_examples:
            examples.append(_format_example(n, row, selected, lang))
            n += 1
    examples_block = "\n\n".join(examples)

    return f"""# Language Detection Agent for {s['languages_joined']} STT

## Role:
   * You are a specialized language detection agent that analyzes outputs from {s['languages_joined']} STT engines.
   * Determine the original language of the speech and identify which STT produced the more accurate transcript.

## Objective:
   * Given transcripts from {s['languages_joined']} STT,
   * Determine the original language of the speech by evaluating transcript quality and linguistic accuracy.

## Instructions:
   * Input Format:
{s['input_format']}

   * Output Format:
      - Output only one of the following values (case-sensitive):
{_output_values_block(selected)}
      - "None" is reserved for truly ambiguous or non-linguistic cases (see below); it is NOT the default.

## Analysis Process:
    * Transcript Quality Assessment:
      - Evaluate linguistic coherence and naturalness of each transcript
      - Check for proper word formation, grammar, and sentence structure
      - Identify mixed-language artifacts (e.g., transliterated speech or phonetic spellings)

    * Language Detection Rules:
      - For each language, the matching STT produces grammatically correct, fluent text while the other STTs show transliterated or phonetically similar text.

        * Ambiguous or Non-Linguistic Speech — Output: "None" **only** if:
            - The input consists only of truly ambiguous or non-linguistic expressions
            - Single words or short phrases without grammatical structure:
              * Proper nouns: names of people (e.g., "rahul", "priya", "sharma")
              * Dates: standalone dates (e.g., "15th january", "2024", "monday")
              * Numbers: phone numbers, dates, codes (e.g., "9876543210", "123")
              * Common interjections: (e.g., "haan ha", "okay hai", "yeah madam", "hmm")
              * Single nouns: standalone objects (e.g., "laptop", "coffee", "book")
              * Mixed casual expressions: (e.g., "okay hai", "yes ji", "haan okay")
            - These expressions lack meaningful grammatical structure (no verbs, no actions, no complete sentence structure)
            - If either transcript shows **even short but clear conversational structure with a verb or complete sentence**, then classify as one of the supported languages — **do not return "None"**

        * Explicit Language Declaration — Always prioritize this:
            * Direct Phrases Indicating Intent:
               - If a transcript (STT output) contains an explicit statement of language preference—such as:
{s['direct_phrases']}
               - Output: matching the declared preference

            * Colloquial Language Words:
               - If the transcript contains common alternate terms:
{s['colloquial']}
               - These should be detected as explicit language intents and mapped accordingly.

            * Priority:
               - If any form of explicit language declaration (as above) appears ANYWHERE in the transcript, that must take precedence—override all other language inference logic.

   * Decision Logic:
      - If input contains only proper nouns, dates, numbers, single words, or interjections without grammatical structure → Output: "None"
      - If one STT is coherent and others are transliterations → Output: the coherent language
      - If multiple transcripts are valid, choose the one with better grammar and fluency
      - If all are ambiguous or contain only non-linguistic entities → Output: "None"

## Sample Examples:

{examples_block}

## IMPORTANT:
   - Output must contain ONLY one of: {", ".join(f'"{lang}"' for lang in selected)}, or "None"
   - Do NOT explain or add extra text — just return the final decision
   - Output "None" for: proper nouns, dates, numbers, single words, interjections, or any input lacking grammatical structure (no verbs, no complete sentences)
   - Do NOT output "None" for grammatically correct full sentences with verbs or actions
   - "None" is reserved strictly for non-linguistic expressions, entities, or inherently ambiguous short phrases
"""


def render_language_switch_prompt(languages: list[str], mode: Mode, custom_prompt: str | None) -> str | None:
    """The single entry point used by prompt.service — resolves `mode` +
    AgentConfig.languages (+ the custom text, for "custom") into the prompt
    text that should actually be sent to the language-switch LLM call, or
    None if the feature doesn't apply (fewer than two configured languages,
    or "custom" with nothing configured yet).
    """
    if mode == "custom":
        return custom_prompt or None

    selected = resolve_selected_languages(languages)
    if len(selected) < 2:
        return None

    if mode == "implicit":
        return render_implicit_prompt(selected)
    return render_explicit_prompt(selected)
