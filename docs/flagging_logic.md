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
- **Output:** redacted text + audit log
- **Latency target:** <50ms
- **NLP model:** en_core_web_sm (11 MB on disk, ~100 MB RAM). See docs/known-deferred.md if upgrade to lg becomes needed.
- **Always runs**, regardless of strategy

### Non-English input handling

`redact_pii(text, language="en")` raises ValueError for non-English input.
Pipeline catches this and degrades gracefully:

- Stage 1a (rules) still runs — Likert scores are language-independent
- Stage 1b (LLM classifier) and Stage 2 (LLM assessment) skip —
  cannot send un-redacted text to external LLM (PII leak)
- If Stage 1a flags: create Assessment with
  llm_status="skipped_non_english"
- Counselor sees rule-based severity + original text for manual review;
  no AI-generated counselor_brief

Rationale: empirical testing showed langdetect misclassifies
informal English (mental-health-typical input) ~69% of the time,
including misclassifying "I want to die" as Afrikaans. Blocking
non-English at API would reject genuine English crisis signals.
Pipeline-level handling is safer and language-agnostic.

### Stage 1a — Rule-based Likert Scoring

Pure Python evaluation against `FlaggingRule` config. No external calls.

**Rule types:**

1. **Single-question threshold:** Flag if any one Likert response exceeds `single_question_threshold` (default 4)
   - Modes: `disabled`, `conservative` (only 5/5), `standard` (4+), `aggressive` (3+, deprecated)
2. **Category sum thresholds:** Flag if sum of Likert values within a category (stress, sleep, support, general) exceeds the per-category threshold
   - Default: `{"stress": 12, "sleep": 10, "support": 8, "general": 14}`

**Severity when rules alone flag:** configurable, default `medium`

### Stage 1b — LLM Classifier

| Mode | Backend | Model |
|---|---|---|
| API (default) | Together.ai | `meta-llama/Llama-Guard-4-12B` |
| Self-hosted (stubbed in v1) | Local Ollama | `llama-guard3:8b` |

- **Output:** safe/unsafe + violated MLCommons hazard categories (S1-S13)
- **Relevant categories for Sowfee:** S11 (Suicide & Self-Harm), S1 (Violent Crimes)
- **Latency target:** <2s (API)
- **Resilience:** Tenacity retry (3x exponential backoff), pybreaker circuit breaker

### Stage 2 — LLM Assessment

Runs only when Stage 1a OR Stage 1b flagged AND strategy includes LLM.

**Model choice is provisional**, pending eval data (see §11). Initial configuration:

| Mode | Primary | Failover |
|---|---|---|
| API | Anthropic `claude-haiku-4-5` | OpenAI `gpt-4o-mini` |
| Self-hosted (stubbed in v1) | Ollama `qwen3:8b` | (none) |

#### Schema enforcement patterns

**Claude Haiku 4.5 (Anthropic):** tool use with `tool_choice={"type": "tool", "name": "submit_assessment"}` forcing the model to call the tool. Tool's `input_schema` is `CrisisAssessment.model_json_schema()`.

**gpt-4o-mini (OpenAI):** `response_format=CrisisAssessment` directly on `client.beta.chat.completions.parse`.

Both equivalently reliable. Abstracted behind the `AssessmentBackend` protocol.

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

Simple severity-driven mapping:

```python
if severity == "high":
    tier = 1  # Page on-call (Tier 1: immediate intervention)
elif severity == "medium":
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

**v1 scope note:** Only `inference_mode="api"` is fully implemented in v1. `hybrid` and `self_hosted` route to Ollama backends that raise `NotImplementedError`. Admin UI should hide non-`api` options until those backends are implemented.

**Note:** `flagging_strategy` (WHAT signals) and `inference_mode` (WHERE AI runs) are orthogonal.

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

**Note:** PHQ-9 and GAD-7 scoring fields were considered but deferred until needed. The `FlaggingRule` model can be extended later without breaking changes.

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
    """Stage 2 LLM output. Kept intentionally minimal."""
    severity: Severity                         # drives tier assignment
    evidence_phrases: list[str]                # must each appear verbatim in source
    primary_concern: str                       # one-line summary
    counselor_brief: str                       # 2-3 sentences for human review
    confidence: float = Field(ge=0.0, le=1.0)  # LLM self-reported
    provider: str                              # e.g. "anthropic/claude-haiku-4-5"
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
    evidence_phrases = models.JSONField(default=list)
    primary_concern = models.CharField(max_length=200, blank=True)
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
        ("skipped_non_english", "Non-English input, LLM skipped"),
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

**Note on `SurveyResponse.flagged`:** the existing boolean field stays as a denormalized cache, updated from `Assessment.tier != None`.

---

## 7. Models & Infrastructure

### AI/ML Models Used

| Stage | Role | Hosting | Model |
|---|---|---|---|
| 0 | PII redaction | Local Python pkg | Presidio (~200MB) |
| 1b API | Classifier | Together.ai | `meta-llama/Llama-Guard-4-12B` |
| 1b self-hosted (stubbed) | Classifier | Ollama EC2 | `llama-guard3:8b` |
| 2 API primary | Assessment | Anthropic | `claude-haiku-4-5` |
| 2 API failover | Assessment | OpenAI | `gpt-4o-mini` |
| 2 self-hosted (stubbed) | Assessment | Ollama EC2 | `qwen3:8b` |
| Eval-only candidate | Assessment | Together.ai | `deepseek-ai/DeepSeek-V4-Flash` |

### v1 Build Scope: API-only

For the 2-day MVP build:
- Only `inference_mode="api"` is fully implemented
- Ollama backends exist as classes but raise `NotImplementedError`
- Self-hosted EC2 infrastructure (m7g.2xlarge) is documented but not provisioned
- When the first FERPA-strict institution requires self-hosted, implement Ollama backends and spin up EC2 — estimated 3-4 hour task

### Self-hosted infrastructure (future)

When triggered: `m7g.2xlarge` (8 vCPU ARM Graviton, 32 GB RAM), shared across all `self_hosted` tenants, ~$236/mo + $3 EBS.

---

## 8. Known Edge Cases (Deferred)

### 8.1 Strategy change during in-flight analysis

**Scenario:** Admin switches `flagging_strategy` while a student's response is being processed by Celery.

**Impact:** Single response analyzed under new strategy. Bounded to surveys in flight during the change.

**Status:** Documented, not fixed.

**Future fix:** Snapshot `flagging_strategy` and config on `SurveyResponse` at submission; Celery task reads from snapshot.

**Trigger to revisit:** Volume >1000 surveys/day, audit trail request, or automated config rotation.

### 8.2 Ollama backends not implemented

**Scenario:** Admin sets `inference_mode="self_hosted"` before implementation.

**Behavior:** `OllamaClassifierBackend.classify()` raises `NotImplementedError` with message pointing to fix.

**Mitigation:** Admin UI in v1 only exposes `inference_mode="api"`. Database accepts other values for future-compatibility.

---

## 9. Cost Summary (at 20 surveys/day projected scale)

| Strategy | Monthly Cost | Breakdown |
|---|---|---|
| `rule_only` | $0 | No external calls; pure local computation |
| `llm_only` | ~$0.10 | Llama Guard 4 ($0.04) + Claude Haiku on ~10% flagged ($0.06) |
| `hybrid` | ~$0.10 | Same as `llm_only` (rules are free) |

---

## 10. Default Flagging Strategy

When a new institution is created:

1. `flagging_strategy = "hybrid"` (recommended default)
2. `inference_mode = "api"` (only fully supported mode in v1)
3. `FlaggingRule` auto-created with conservative defaults (see §5)

Admins can change `flagging_strategy` and `FlaggingRule` settings via Django admin. `inference_mode` is gated to `api` in admin UI until Ollama backends ship.

---

## 11. Model Selection: Eval-Driven Decision

**Stage 2 primary model selection is provisional**, confirmed by Phase 6 eval data.

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
- Candidate produces materially better `counselor_brief` output (qualitative), OR
- Cost-adjusted value decisively favors a different candidate at projected scale

If models are within ~5 points on all metrics, **stick with provisional choice** (Haiku).

### DeepSeek V4-Flash specific consideration

DeepSeek V4-Flash lacks schema-enforced output. If it performs competitively, production use requires a retry-on-schema-drift wrapper.

---

## 12. Open Questions & Future Work

- [ ] Implement Ollama backends when first self-hosted institution signs
- [ ] Memory / risk score with exponential decay (longitudinal trajectory)
- [ ] Counselor review queue UI (frontend)
- [ ] Real-time chat moderation pipeline (separate design)
- [ ] Triage agent for tier routing decisions
- [ ] Fine-tuning Llama Guard on Sowfee-specific labeled data
- [ ] Admin "preview" tool to test threshold changes
- [ ] Snapshot strategy at submission (race fix when volume justifies)
- [ ] Cross-tenant isolation tests for `Assessment` model
- [ ] Re-evaluate Stage 2 primary based on eval data

---

## 13. References

- [Llama Guard 4 Model Card](https://huggingface.co/meta-llama/Llama-Guard-4-12B)
- [Anthropic Claude Haiku docs](https://docs.anthropic.com/)
- [OpenAI gpt-4o-mini docs](https://platform.openai.com/docs/models)
- [Microsoft Presidio Documentation](https://microsoft.github.io/presidio/)
- [MLCommons Safety Taxonomy](https://arxiv.org/abs/2503.05731)

---

## Changelog

**2026-05-12 (v3):**
- Simplified `CrisisAssessment` from 10 fields to 7. Removed: `cssrs_level` (no clinician validation in MVP), `needs_support` (redundant with `severity`), `risk_factors` (no consumer yet).
- Simplified `tier` mapping: purely severity-driven, no `cssrs_level` branch.
- Simplified `FlaggingRule`: removed `use_phq9` and `use_gad7` toggles (not needed in MVP).
- Removed `Assessment` model fields: `cssrs_level`, `needs_support`, `risk_factors`.
- Added §7 "v1 Build Scope: API-only" — explicit acknowledgment that Ollama backends are stubs.
- Added §8.2 — Ollama not implemented as documented edge case.

**2026-05-12 (v2):**
- Stage 2 primary: `gpt-4o-mini` → `claude-haiku-4-5`
- Stage 2 failover: `claude-haiku` → `gpt-4o-mini` (flipped)
- Added §11 (Model Selection: Eval-Driven Decision)
- Added DeepSeek V4-Flash as eval-only experimental candidate
- Cost summary updated.

**Initial:** Design locked.