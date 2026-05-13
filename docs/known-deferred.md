## PII redaction: NER model size

v1 uses en_core_web_sm (~11 MB, ~100 MB RAM) for minimal footprint.
NER F-score ~0.81 vs ~0.85 for en_core_web_lg (~750 MB).

If production data shows PERSON/LOCATION recall too low,
upgrade to en_core_web_md (~48 MB) or en_core_web_lg (~750 MB).
Change one config line + re-download model.

## Multi-language LLM analysis

v1 only does LLM analysis for English. Non-English responses degrade
to rule-only flagging with counselor manual review.

Empirical evidence: langdetect on informal English misclassifies ~69%
of the time, so API-layer language gating would block genuine English
crisis signals. Therefore non-English handling is at pipeline layer
(graceful degrade) instead of API layer (block).

Trigger to revisit: First international institution signs requiring
LLM analysis in their student population's language. At that point,
implement per-language pipeline routing with appropriate spaCy models
+ multilingual LLM Stage 2.

## Strategy change race
Admin switching strategy mid-Celery-task uses new strategy.
Bounded to in-flight surveys. Fix when volume > 1K/day.

## Ollama backends
inference_mode="self_hosted" raises NotImplementedError.
Admin UI only shows "api" option. Fix when first self-hosted institution signs.
