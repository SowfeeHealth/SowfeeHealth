# Flagging Logic — Sowfee Crisis Detection Pipeline

**Status:** Design locked — ready for implementation
**Branch:** `feat/moderation-v2`
**Last updated:** 2026-05-12

---

## 1. Overview

Sowfee's crisis detection pipeline analyzes student survey responses to identify students who may need mental health support. The system supports three configurable flagging strategies, selected per-institution by admins via a dropdown plus an optional Advanced Settings panel.

| Strategy | Stage 1 Signals | LLM Used | Cost (20/day) | Best for |
|---|---|---|---|---|
| `rule_only` | Likert thresholds | No | $0 | Clinical settings, strict privacy DPAs, no-AI policies |
| `llm_only` | LLM classifier + assessment | Yes | ~$0.10/mo | Text-heavy surveys, novel instruments |
| `hybrid` (default) | Both Likert + LLM | Yes | ~$0.10/mo | Most institutions |

Default for new institutions: **`hybrid`**.

---

## 2. Pipeline Architecture

```
Survey response submitted
        │
        ▼
┌─────────────────────────────────────────────┐
│ Stage 0 — PII Redaction (always runs)       │
│ Microsoft Presidio (local, free, ~10ms)     │
└─────────────────────────────────────────────┘
        │
        ├─────────────────┬─────────────────────┐
        ▼                 ▼                     │
┌───────────────┐  ┌──────────────────┐         │
│ Stage 1a      │  │ Stage 1b         │         │
│ Rule-based    │  │ LLM Classifier   │         │
│ Likert scores │  │ Llama Guard 4    │         │
│ (if needed)   │  │ (if needed)      │         │
└───────────────┘  └──────────────────┘         │
        │                 │                     │
        └────────┬────────┘                     │
                 ▼                              │
       Either flagged? ─── no ──→ Save clean ──┘
                 │
                 ▼ yes (and if LLM in strategy)
┌─────────────────────────────────────────────┐
│ Stage 2 — LLM Assessment                    │
│ Claude Haiku 4.5 (primary)                  │
│ + rule scores as context                    │
└─────────────────────────────────────────────┘
                 │
                 ▼
       Combine signals → final severity
                 │
                 ▼
       Tier assignment → DB write → Counselor queue
```

### When each stage runs by strategy

| Strategy | Stage 0 | Stage 1a (Rules) | Stage 1b (LLM Classify) | Stage 2 (LLM Assess) |
|---|---|---|---|---|
| `rule_only` | ✓ | ✓ | — | — |
| `llm_only` | ✓ | — | ✓ | If 1b flagged |
| `hybrid` | ✓ | ✓ | ✓ | If 1a OR 1b flagged |

---

## 3. Stage Details

### Stage 0 — PII Redaction

- **Library:** `presidio-analyzer` + `presidio-anonymizer` (Microsoft, open source)
- **Hosting:** Local Python package, runs in Celery worker
- **Entities redacted:** PERSON, PHONE_NUMBER, EMAIL_ADDRESS, US_SSN, CREDIT_CARD, IP_ADDRESS, URL, LOCATION
- **Placeholders:** Typed (e.g., `[PERSON_NAME]`, `[PHONE]`) — preserves semantic class for LLM
- **Custom recognizer stub:** Institution-specific student IDs (regex per tenant)
- **Output:** redacted text + audit log
- **Latency target:** <50ms
- **Always runs**, regardless of strategy

### Stage 1a — Rule-based Likert Scoring

Pure Python evaluation against `FlaggingRule` config. No external calls.

**Rule types:**

1. **Single-question threshold:** Flag if any one Likert response exceeds `single_question_threshold` (default 4)
   - Modes: `disabled`, `conservative` (only 5/5), `standard` (4+), `aggressive` (3+, deprecated)
2. **Category sum thresholds:** Flag if sum of Likert values within a category (stress, sleep, support, general) exceeds the per-category threshold
   - Default: `{"stress": 12, "sleep": 10, "support": 8, "general": 14}`
3. **Validated instrument scoring (future):** PHQ-9, GAD-7 cutoffs — toggles, off by default

**Severity when rules alone flag:** configurable, default `medium`

### Stage 1b — LLM Classifier

| Mode | Backend | Model |
|---|---|---|
| API (default) | Together.ai | `meta-llama/Llama-Guard-4-12B` |
| Hybrid | Together.ai | Same |
| Self-hosted | Local Ollama | `llama-guard3:8b` |

- **Output:** safe/unsafe + violated MLCommons hazard categories (S1-S13)
- **Relevant categories for Sowfee:** S11 (Suicide & Self-Harm), S1 (Violent Crimes)
- **Latency target:** <2s (API), <5s (self-hosted CPU)
- **Resilience:** Tenacity retry (3x exponential backoff), pybreaker circuit breaker

### Stage 2 — LLM Assessment

Runs only when Stage 1a OR Stage 1b flagged AND strategy includes LLM.

**Model choice is provisional**, pending eval data (see §11). Initial configuration:

| Mode | Primary | Failover |
|---|---|---|
| API | Anthropic `claude-haiku-4-5` | OpenAI `gpt-4o-mini` |
| Self-hosted | Ollama `qwen3:8b` | (none) |

**Rationale for Claude Haiku as primary:**
- Slight edge on nuanced clinical-adjacent reasoning (Anthropic safety optimization)
- Schema-enforced structured output via tool use (equivalent to OpenAI's `response_format`)
- Vendor diversity from Together.ai (Stage 1) — different infrastructure than OpenAI

**Rationale for gpt-4o-mini as failover:**
- Different vendor for resilience (uncorrelated outages)
- Faster, cheaper, equally capable on this task
- Same Pydantic schema works with `response_format` — easy to maintain

**Additional experimental candidate** (Phase 6 eval only, not in production pipeline yet):
- DeepSeek V4-Flash via Together.ai (`deepseek-ai/DeepSeek-V4-Flash`)
- Trade-off: no native schema enforcement (JSON via prompting), but capable model and cheap
- If it outperforms Haiku/gpt-4o-mini on eval, consider promoting to production with retry-on-schema-drift wrapper

#### Schema enforcement patterns

**Claude Haiku 4.5 (Anthropic):** tool use
```python
ASSESSMENT_TOOL = {
    "name": "submit_assessment",
    "description": "Submit the crisis assessment",
    "input_schema": CrisisAssessment.model_json_schema(),
}

response = await client.messages.create(
    model="claude-haiku-4-5",
    tools=[ASSESSMENT_TOOL],
    tool_choice={"type": "tool", "name": "submit_assessment"},
    messages=[{"role": "user", "content": prompt}],
)
tool_use = next(b for b in response.content if b.type == "tool_use")
assessment = CrisisAssessment(**tool_use.input)
```

**gpt-4o-mini (OpenAI):** response_format
```python
response = await client.beta.chat.completions.parse(
    model="gpt-4o-mini",
    response_format=CrisisAssessment,
    messages=[{"role": "user", "content": prompt}],
)
assessment = response.choices[0].message.parsed
```

Both equivalently reliable. Abstracted behind the `AssessmentBackend` protocol so the pipeline doesn't care which is in use.

- **Context passed in:** redacted text, rule scores by category, Likert summary, question text
- **Evidence grounding:** Required — every `evidence_phrase` must appear verbatim in source. Validated post-hoc; rejected assessments retry once with stronger prompt.
- **Latency target:** <5s

---

## 4. Signal Combination & Tier Mapping

### Combination Rules (Hybrid mode)

When both signals run, the final severity is determined by:

1. Neither flags → no Assessment row, return clean
2. Both flag → highest severity wins, `agreement = "both"` (high-confidence flag)
3. Only one flags → use that signal's severity, `agreement = "rule_only"` or `"llm_only"`
4. Disagreement on severity → resolve per `FlaggingRule.on_disagreement`:
   - `higher` (default): use higher severity
   - `lower`: use lower severity (conservative flagging)
   - `review`: always route to human review queue

### Tier Assignment

```
if severity == "high" or cssrs_level >= 4:
    tier = 1  # Page on-call (Tier 1: immediate intervention)
elif severity == "medium" or agreement == "both":
    tier = 2  # Counselor queue (Tier 2: review within 24h)
elif severity == "low":
    tier = 3  # Log + dashboard monitor (Tier 3: trend tracking)
else:
    tier = None  # Not flagged
```

### LLM Degraded Mode (Fail-Open)

When the LLM is unavailable (circuit breaker open, all retries exhausted across both primary and failover) and Stage 1 flagged:
- Skip Stage 2
- Assign tier based on Stage 1 severity alone, **bumped up one level** (fail-open principle: prefer over-paging to missing crises)
- Set `llm_status = "degraded"` for visibility
- Queue for later re-analysis when LLM recovers

---

## 5. Configuration Data Model

### Top-level: `Institution.flagging_strategy`

```python
class Institution(TenantMixin):
    # ... existing fields

    FLAGGING_STRATEGIES = [
        ("rule_only", "Rule-based (Likert only)"),
        ("llm_only", "AI text analysis only"),
        ("hybrid", "Hybrid (recommended)"),
    ]
    flagging_strategy = models.CharField(
        max_length=20,
        choices=FLAGGING_STRATEGIES,
        default="hybrid",
    )

    INFERENCE_MODES = [
        ("api", "API (Together + Anthropic)"),
        ("hybrid", "Self-hosted Stage 1, API Stage 2"),
        ("self_hosted", "Fully self-hosted"),
    ]
    inference_mode = models.CharField(
        max_length=20,
        choices=INFERENCE_MODES,
        default="api",
        help_text="Where AI inference runs (compute backend choice)",
    )
```

**Note:** `flagging_strategy` (WHAT signals) and `inference_mode` (WHERE AI runs) are orthogonal. Some combinations are no-ops (e.g., `rule_only` + `self_hosted` doesn't use AI infrastructure even if provisioned).

### Advanced: `FlaggingRule` (one-to-one with Institution)

```python
class FlaggingRule(models.Model):
    institution = models.OneToOneField(
        Institution,
        related_name="flagging_rule",
        on_delete=models.CASCADE,
    )

    # ── Stage 1a: Rule-based scoring ──
    single_question_mode = models.CharField(
        max_length=20,
        choices=[
            ("disabled", "Disabled"),
            ("conservative", "Flag only on max value 5/5"),
            ("standard", "Flag on 4+"),
            ("aggressive", "Flag on 3+ (not recommended)"),
        ],
        default="standard",
    )
    single_question_threshold = models.IntegerField(default=4)
    category_sum_thresholds = models.JSONField(default=dict)
    use_phq9 = models.BooleanField(default=False)
    use_gad7 = models.BooleanField(default=False)
    rule_severity = models.CharField(
        max_length=10,
        choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")],
        default="medium",
    )

    # ── Stage 1b/2: AI analysis ──
    evidence_grounding = models.CharField(
        max_length=20,
        choices=[("strict", "Strict"), ("permissive", "Permissive")],
        default="strict",
    )

    # ── Hybrid signal combination ──
    on_disagreement = models.CharField(
        max_length=20,
        choices=[
            ("higher", "Use higher severity"),
            ("lower", "Use lower severity"),
            ("review", "Send to human review"),
        ],
        default="higher",
    )

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )
```

### Defaults at institution creation

A `FlaggingRule` is auto-created (via signal) with conservative defaults:

```python
{
    "single_question_mode": "conservative",
    "single_question_threshold": 5,
    "category_sum_thresholds": {
        "stress": 12,
        "sleep": 10,
        "support": 8,
        "general": 14,
    },
    "use_phq9": False,
    "use_gad7": False,
    "rule_severity": "medium",
    "evidence_grounding": "strict",
    "on_disagreement": "higher",
}
```

**Principle:** Default toward fewer false positives; admins can tune up sensitivity if their population warrants it.

---

## 6. Output Schemas

### Pydantic Contracts (between backends)

```python
class Severity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class HazardCategory(str, Enum):
    SUICIDE_SELF_HARM = "S11"
    VIOLENT_CRIMES = "S1"
    # ... S2-S14

class ClassifierResult(BaseModel):
    flagged: bool
    categories: list[HazardCategory]
    confidence: float = Field(ge=0.0, le=1.0)
    raw_output: str
    latency_ms: int
    provider: str

class RuleResult(BaseModel):
    flagged: bool
    triggers: list[str]                        # ["single:Q5=5", "category:stress=15>12"]
    category_scores: dict[str, int]            # {"stress": 15, "sleep": 7}
    severity: Severity
    latency_ms: int

class CrisisAssessment(BaseModel):
    severity: Severity
    cssrs_level: int = Field(ge=0, le=5)
    evidence_phrases: list[str]                # must each appear verbatim in source
    needs_support: bool
    primary_concern: str
    risk_factors: list[str]
    counselor_brief: str
    confidence: float = Field(ge=0.0, le=1.0)
    provider: str
    latency_ms: int

class TierAssignment(BaseModel):
    tier: int = Field(ge=1, le=3)
    urgency_window: str
    notification_channels: list[str]
    reasoning: str
```

### Django Storage Model: `Assessment`

```python
class Assessment(models.Model):
    survey_response = models.OneToOneField(
        SurveyResponse,
        on_delete=models.CASCADE,
        related_name="assessment",
    )

    # Stage 1a result
    rule_flagged = models.BooleanField(default=False)
    rule_triggers = models.JSONField(default=list)
    rule_category_scores = models.JSONField(default=dict)

    # Stage 1b result
    llm_classifier_flagged = models.BooleanField(default=False)
    llm_classifier_categories = models.JSONField(default=list)

    # Stage 2 result (nullable; only when LLM ran and flagged)
    severity = models.CharField(max_length=10, null=True, blank=True)
    cssrs_level = models.IntegerField(null=True, blank=True)
    evidence_phrases = models.JSONField(default=list)
    needs_support = models.BooleanField(null=True)
    primary_concern = models.CharField(max_length=200, blank=True)
    risk_factors = models.JSONField(default=list)
    counselor_brief = models.TextField(blank=True)
    confidence = models.FloatField(null=True, blank=True)

    # Combination metadata
    flag_sources = models.JSONField(default=list)         # ["rule", "llm"]
    agreement = models.CharField(max_length=20, null=True, blank=True)

    # Tier routing
    tier = models.IntegerField(null=True, blank=True)

    # Operational state
    LLM_STATUS_CHOICES = [
        ("complete", "Complete"),
        ("degraded", "LLM unavailable, Stage 1 only"),
        ("pending_retry", "Queued for retry"),
        ("failed", "Failed permanently"),
    ]
    llm_status = models.CharField(
        max_length=20,
        choices=LLM_STATUS_CHOICES,
        default="complete",
    )
    stage1_provider = models.CharField(max_length=50, blank=True)
    stage2_provider = models.CharField(max_length=50, blank=True)

    # Counselor review
    counselor_reviewed_at = models.DateTimeField(null=True, blank=True)
    counselor_override = models.JSONField(null=True, blank=True)

    # Audit
    raw_assessment = models.JSONField(default=dict)
    redaction_audit = models.JSONField(default=list)
    total_latency_ms = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "surveys"
        indexes = [
            models.Index(fields=["tier", "counselor_reviewed_at"]),
            models.Index(fields=["llm_status", "created_at"]),
        ]
```

**Note on `SurveyResponse.flagged`:** the existing boolean field stays as a denormalized cache, updated from `Assessment.tier != None`. New code reads `Assessment` as source of truth; legacy queries on `flagged` continue to work.

---

## 7. Models & Infrastructure

### AI/ML Models Used

| Stage | Role | Hosting | Quantization | Size |
|---|---|---|---|---|
| 0 | PII redaction | Local Python pkg | N/A | ~200MB |
| 1b API | Classifier | Together.ai | Provider's | ~12B params (Llama Guard 4) |
| 1b self-hosted | Classifier | Ollama EC2 | Q4_K_M | 4.7GB disk, ~5.5GB RAM (Llama Guard 3 8B) |
| 2 API primary | Assessment | Anthropic | Provider's | Claude Haiku 4.5 (small/fast tier) |
| 2 API failover | Assessment | OpenAI | Provider's | gpt-4o-mini (~8B-class rumored) |
| 2 self-hosted | Assessment | Ollama EC2 | Q4_K_M | Qwen 3 8B — 4.9GB disk, ~5.8GB RAM |
| Eval-only candidate | Assessment | Together.ai | Provider's | DeepSeek V4-Flash (284B/13B activated MoE) |

### Self-hosted Infrastructure (when needed)

**Recommended instance:** `m7g.2xlarge` (8 vCPU ARM Graviton, 32 GB RAM)
- Runs both Stage 1b (Llama Guard 3 8B) and Stage 2 (Qwen 3 8B) via Ollama
- Both models always resident (`OLLAMA_KEEP_ALIVE=-1`)
- Peak RAM usage: ~16 GB; comfortable 8 GB headroom
- 24/7 cost: ~$236/mo + $3 EBS
- Shared across all `self_hosted` institutions (model is stateless inference)

**Demo-only setup:** `t3.xlarge` with stop/start AMI, ~$7/mo

**Local dev:** Run Ollama on local machine, expose via cloudflared if needed

---

## 8. Known Edge Cases (Deferred)

### 8.1 Strategy change during in-flight analysis

**Scenario:** Admin switches `flagging_strategy` while a student's response is being processed by Celery.

**Race window:** ~5-30 seconds (Celery latency between enqueue and execution)

**Impact:** Single response analyzed under new strategy instead of strategy active at submission. Bounded to surveys in flight during the change.

**Status:** Documented, not fixed.

**Reasoning to defer:**
- Probability is extremely low (admin changes are rare, ~1/year)
- Impact ceiling is one response per change event
- Engineering cost (snapshot field + migration + task signature change + tests) > expected value at current scale

**Future fix when justified:**
1. Add `flagging_strategy_at_submission` and `flagging_config_snapshot` fields to `SurveyResponse`
2. Set them at submission time in `_handle_student_responses`
3. Celery task reads from snapshot, not current `Institution.flagging_strategy`
4. Bonus: permanent audit trail of "which strategy was used for this response"

**Trigger to revisit:**
- Volume exceeds 1000 surveys/day, OR
- Institution explicitly requests auditability, OR
- Automated strategy changes are introduced (scheduled config rotations)

### 8.2 Advanced settings changes during in-flight analysis

Same race applies to `FlaggingRule` field changes. Same deferral. Fix is also via snapshotting.

---

## 9. Cost Summary (at 20 surveys/day projected scale)

| Strategy | Monthly Cost | Breakdown |
|---|---|---|
| `rule_only` | $0 | No external calls; pure local computation |
| `llm_only` | ~$0.10 | Llama Guard 4 ($0.04) + Claude Haiku on ~10% flagged ($0.06) |
| `hybrid` | ~$0.10 | Same as `llm_only` (rules are free) |

Self-hosted institutions add ~$236/mo for shared `m7g.2xlarge` (regardless of how many self-hosted tenants share it, up to ~5000 surveys/day total).

**Cost note:** Claude Haiku is ~5x more expensive per output token than gpt-4o-mini. At 20 surveys/day this is negligible (cents/month difference). At 10K+ surveys/day, the gap becomes ~$100-300/month — worth re-evaluating primary at that scale, especially if eval shows the models are functionally tied.

---

## 10. Default Flagging Strategy Selection Logic

When a new institution is created:

1. `flagging_strategy = "hybrid"` (the recommended default)
2. `inference_mode = "api"` (cheapest deployment)
3. `FlaggingRule` auto-created with conservative defaults (see §5)

Admins can change any of these via the Django admin interface or a dedicated settings page (Phase 7 deliverable).

---

## 11. Model Selection: Eval-Driven Decision

**Stage 2 primary model selection is provisional** and will be confirmed by Phase 6 eval data.

### Provisional choice
- **Primary:** Anthropic Claude Haiku 4.5
- **Failover:** OpenAI gpt-4o-mini
- **Experimental candidate:** DeepSeek V4-Flash via Together.ai

### Eval methodology (Phase 6)

For each example in the eval set, run all three candidates and compute:
- Recall per severity tier (especially high-severity)
- False positive rate
- Evidence-grounding pass rate (% of evidence_phrases that appear verbatim in source)
- Schema validation pass rate (% of outputs that parse cleanly into Pydantic)
- Latency p50/p95
- Manual qualitative review of `counselor_brief` text (sample of 10-15)

### Decision criteria

Re-designate primary if:
- Candidate exceeds current primary on high-severity recall by >5 points, OR
- Candidate matches primary on recall but produces materially better `counselor_brief` output (qualitative), OR
- Cost-adjusted value (recall/cost) decisively favors a different candidate at projected scale

If models are within ~5 points on all metrics, **stick with provisional choice** (Haiku). Vendor diversification (Anthropic for Stage 2, Together for Stage 1) and slight clinical-nuance edge are tiebreakers.

### DeepSeek V4-Flash specific consideration

If DeepSeek V4-Flash performs competitively but lacks schema-enforced output, the path to production includes a retry-on-schema-drift wrapper:

```python
async def assess_with_retry(text, max_attempts=2):
    for attempt in range(max_attempts):
        raw = await deepseek_client.chat.completions.create(...)
        try:
            return CrisisAssessment.model_validate_json(raw)
        except ValidationError as e:
            if attempt + 1 == max_attempts:
                raise
            # Re-prompt with error context for next attempt
            continue
```

Acceptable trade-off if recall numbers justify it.

---

## 12. Open Questions & Future Work

- [ ] Memory / risk score with exponential decay (longitudinal trajectory analysis)
- [ ] Counselor review queue UI (frontend, separate from this build)
- [ ] Real-time chat moderation pipeline (separate design, see README diagram)
- [ ] Triage agent for tier routing decisions (when caseload variability justifies)
- [ ] Fine-tuning Llama Guard on Sowfee-specific labeled data (when 500+ labels collected)
- [ ] Admin "preview" tool to test threshold changes against sample responses
- [ ] Snapshot strategy at submission (race fix when volume justifies — see §8.1)
- [ ] Cross-tenant isolation tests for `Assessment` model (Phase 9 deliverable)
- [ ] Per-question category tagging UI for admins (for rule scoring)
- [ ] Re-evaluate Stage 2 primary based on eval data (see §11)

---

## 13. References

- [Llama Guard 4 Model Card](https://huggingface.co/meta-llama/Llama-Guard-4-12B)
- [Llama Guard 3 8B Model Card](https://huggingface.co/meta-llama/Meta-Llama-Guard-3-8B)
- [Anthropic Claude Haiku docs](https://docs.anthropic.com/)
- [OpenAI gpt-4o-mini docs](https://platform.openai.com/docs/models)
- [DeepSeek V4 Model Card](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro)
- [C-SSRS (Columbia Suicide Severity Rating Scale)](https://cssrs.columbia.edu/)
- [PHQ-9 Patient Health Questionnaire](https://www.apa.org/depression-guideline/patient-health-questionnaire.pdf)
- [GAD-7 Generalized Anxiety Disorder Scale](https://www.apa.org/depression-guideline/anxiety-disorder.pdf)
- [Microsoft Presidio Documentation](https://microsoft.github.io/presidio/)
- [MLCommons Safety Taxonomy](https://arxiv.org/abs/2503.05731)
