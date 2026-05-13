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


async def redact_pii(text: str) -> tuple[str, list[dict]]:
    results = _analyzer.analyze(text=text, entities=_ENTITIES, language="en")

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
