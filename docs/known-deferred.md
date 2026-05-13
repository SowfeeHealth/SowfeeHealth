## PII redaction: NER model size

v1 uses en_core_web_sm (~11 MB, ~100 MB RAM) for minimal footprint.
NER F-score ~0.81 vs ~0.85 for en_core_web_lg (~750 MB).

If production data shows PERSON/LOCATION recall too low,
upgrade to en_core_web_md (~48 MB) or en_core_web_lg (~750 MB).
Change one config line + re-download model.

## Multi-language PII redaction
Only English supported. Other languages raise ValueError.
Fix: install spaCy model, add to _SUPPORTED_LANGUAGES set.

## Strategy change race
Admin switching strategy mid-Celery-task uses new strategy.
Bounded to in-flight surveys. Fix when volume > 1K/day.

## Ollama backends
inference_mode="self_hosted" raises NotImplementedError.
Admin UI only shows "api" option. Fix when first self-hosted institution signs.
