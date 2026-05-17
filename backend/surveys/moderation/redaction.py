import asyncio

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

_ENTITIES = [
    "PERSON",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "US_SSN",
    "CREDIT_CARD",
    "IP_ADDRESS",
    "URL",
    "LOCATION",
]

_PLACEHOLDERS = {
    "PERSON": "[PERSON_NAME]",
    "PHONE_NUMBER": "[PHONE]",
    "EMAIL_ADDRESS": "[EMAIL]",
    "US_SSN": "[SSN]",
    "CREDIT_CARD": "[CREDIT_CARD]",
    "IP_ADDRESS": "[IP]",
    "URL": "[URL]",
    "LOCATION": "[LOCATION]",
}

_NLP_CONFIG = {
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
}
_nlp_engine = NlpEngineProvider(nlp_configuration=_NLP_CONFIG).create_engine()
_analyzer = AnalyzerEngine(nlp_engine=_nlp_engine, supported_languages=["en"])
_anonymizer = AnonymizerEngine()

_OPERATORS = {
    entity: OperatorConfig("replace", {"new_value": placeholder})
    for entity, placeholder in _PLACEHOLDERS.items()
}

_SUPPORTED_LANGUAGES = {"en"}


def _redact_sync(text: str, language: str) -> tuple[str, list[dict]]:
    """CPU-bound Presidio NER + anonymization. Called via asyncio.to_thread."""
    results = _analyzer.analyze(text=text, entities=_ENTITIES, language=language)

    audit_log = [
        {
            "entity_type": r.entity_type,
            "start": r.start,
            "end": r.end,
            "original": text[r.start : r.end],
            "replacement": _PLACEHOLDERS[r.entity_type],
        }
        for r in results
    ]

    anonymized = _anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators=_OPERATORS,
    )

    return anonymized.text, audit_log


async def redact_pii(text: str, language: str = "en") -> tuple[str, list[dict]]:
    """Redact PII from text using Presidio. Async-safe (offloads to thread pool)."""
    if language not in _SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Language '{language}' not supported. "
            f"Supported: {sorted(_SUPPORTED_LANGUAGES)}. "
            f"See docs/known-deferred.md for adding languages."
        )
    return await asyncio.to_thread(_redact_sync, text, language)
