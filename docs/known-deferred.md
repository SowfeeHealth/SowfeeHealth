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

## Ollama backends (Self-hosted inference)

**Status**: Stubbed in v1. `factory.get_classifier/get_assessor` raise 
NotImplementedError when `inference_mode="self_hosted"`.

**Trigger to implement**: First institution requiring on-premise inference
(FERPA-strict, HIPAA-strict, or institutional policy against cloud LLM).

**Estimated effort**: 1-2 days
- Implement OllamaClassifierBackend (Llama Guard 4 self-hosted)
- Implement OllamaAssessmentBackend (Llama 3.1 70B or similar)
- Add Ollama service to docker-compose
- Smoke test on local hardware (4090 / H100 minimum for 70B)
- Verify factory routing
- Add deployment docs for institutional IT

**Why not in v1**: 
1. No prospective tenants currently require self-hosted
2. Cloud API path (Anthropic + OpenAI failover) covers 99% of use cases  
3. Self-hosted adds infra complexity (GPU provisioning, model versioning, 
   uptime monitoring) without revenue justification at MVP stage
4. Best implemented when first paying customer specifies requirement
   (avoid speculative engineering)

**Pre-requisites when triggered**: 
- Tenant signs contract / pilot agreement
- IT specs available (which GPU, network topology, retention policy)
- Validate Ollama can serve concurrent requests at expected QPS