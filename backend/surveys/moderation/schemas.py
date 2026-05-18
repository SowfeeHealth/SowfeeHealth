from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Severity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


SEVERITY_ORDER = {
    Severity.NONE: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
}


class RuleResult(BaseModel):
    flagged: bool
    category_scores: dict[str, int]
    triggered_rules: list[str]
    suggested_severity: Severity
    latency_ms: int


class KeywordResult(BaseModel):
    """Stage 1c keyword filter result.

    Substring match against ~100 distress phrases (suicide / self-harm /
    hopelessness PLUS self-deprecation, academic distress, social
    isolation, emotional exhaustion). Case-insensitive.

    Audit-only in normal operation; matches are recorded for clinical
    review. Acts as a degraded-mode safety net: when Stage 2 LLM both
    providers fail and a crisis keyword matched, QuestionAssessment.
    severity_max() escalates to HIGH so the signal is preserved.
    """
    matched: bool = Field(
        ...,
        description="Whether any keyword matched in the text."
    )
    matched_keywords: list[str] = Field(
        default_factory=list,
        description="Phrases that matched, for audit / debugging."
    )
    latency_ms: int = Field(
        ...,
        description="Wall-clock duration of the match operation."
    )


class LikertResponse(BaseModel):
    """Single Likert question + student's answer. Built by pipeline from DB."""
    question: str = Field(..., description="The question text as asked.")
    answer_choices: dict[int, str] = Field(
        ...,
        description="Mapping of numeric values to text labels.",
    )
    category: str = Field(
        ...,
        description="Institution-tagged category (e.g. 'sleep', 'depression').",
    )
    answer: int = Field(..., description="The numeric value the student chose.")


class FlaggingRule(BaseModel):
    """Institution-level rule for Stage 1a flagging.

    Supports three rule types covering main clinical screening patterns:
    - any_question: WILDCARD - evaluates each Likert answer across ALL
        categories (rule.category is ignored). Use for catching single
        severe symptoms regardless of which category they're in.
        (e.g. any answer >= 4 → medium, catching one Poor/Very Poor response
        even when category averages are within normal range)
    - sum: category total sum vs threshold
        (e.g. PHQ-9 total >= 15 → moderately severe)
    - average: category mean vs threshold
        (e.g. custom surveys with variable question count per category)
    """
    category: str = Field(
        ...,
        description=(
            "Likert category this rule applies to. Sowfee defaults: "
            "general / sleep / support / stress. Institutions can define "
            "custom categories (e.g. 'depression', 'anxiety') as needed. "
            "Ignored for rule_type='any_question' (wildcard); normalized "
            "to 'any' by validator for that rule type."
        ),
    )
    rule_type: Literal["any_question", "sum", "average"] = Field(
        ...,
        description=(
            "'any_question': wildcard, any answer across ALL categories vs threshold. "
            "'sum': sum of answers in category vs threshold. "
            "'average': mean of answers in category vs threshold."
        ),
    )
    threshold: float = Field(
        ...,
        description=(
            "Score threshold. Integer for any_question/sum, "
            "can be non-integer for average."
        ),
    )
    comparison: Literal["gte", "lte"] = Field(
        ...,
        description=(
            "'gte' = score >= threshold triggers. "
            "'lte' = score <= threshold triggers (e.g. low sleep is bad)."
        ),
    )
    severity: Severity = Field(
        ...,
        description="Severity assigned when this rule triggers."
    )
    description: str | None = Field(
        default=None,
        description="Human-readable rule description for counselor / audit log."
    )

    @model_validator(mode='after')
    def normalize_any_question_category(self):
        """For any_question rule type, force category='any' for clarity.

        The rule engine ignores rule.category for any_question (wildcard
        semantics), but standardizing the stored value as 'any' makes
        admin UI display unambiguous.
        """
        if self.rule_type == 'any_question' and self.category != 'any':
            # Could raise here, but choosing to normalize silently —
            # keeps Django model save() flexible
            self.category = 'any'
        return self


class LikertSummary(BaseModel):
    """Institution-level scoring rubric or instrument indicator."""
    scale: str = Field(
        ...,
        description="Instrument name ('PHQ-9') or custom scoring rule.",
    )


class AssessmentOutput(BaseModel):
    """LLM-facing schema for Stage 2 structured output.

    Shared between Anthropic backend (via .model_json_schema() →
    tool input_schema) and OpenAI backend (via response_format).
    Backend wraps this in CrisisAssessment after validation by adding
    latency_ms and provider.
    """
    severity: Literal["none", "low", "medium", "high"] = Field(
        description="Overall clinical severity. Use 'high' for explicit self-harm."
    )
    evidence_phrases: list[str] = Field(
        max_length=5,
        description=(
            "Verbatim phrases from student_response that justify the severity. "
            "MUST appear word-for-word in student_response. Do not paraphrase. "
            "Empty list if severity is 'none'."
        ),
    )
    primary_concern: Literal[
        "suicide_self_harm", "depression", "anxiety", "trauma",
        "substance_use", "interpersonal", "academic_stress",
        "other", "none",
    ] = Field(description="The primary clinical category of concern.")
    counselor_brief: str = Field(
        max_length=600,
        description=(
            "One-paragraph clinical summary for counselor. "
            "Focus on clinically actionable info. Non-jargon language."
        ),
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in this assessment, 0.0-1.0."
    )


class CrisisAssessment(BaseModel):
    severity: Severity
    evidence_phrases: list[str]
    primary_concern: str
    counselor_brief: str
    confidence: float = Field(ge=0.0, le=1.0)
    provider: str
    latency_ms: int


class QuestionAssessment(BaseModel):
    """Per-text-question pipeline output."""
    question_id: int
    redacted_text: str
    keyword_result: KeywordResult | None
    assessment: CrisisAssessment | None
    degraded_mode: bool = False
    degraded_reason: str | None = None

    def severity_max(self) -> Severity:
        """Resolve severity for this single text question.

        Stage 1a (rule engine) is survey-level, not per-question, so it
        is NOT considered here. Rule-driven severity is aggregated at the
        SurveyAssessmentResult level via process_survey(), in parallel
        with each question's severity_max(). Final survey severity =
        max(rule_severity, *per_question_severities).

        Normal mode:
          - assessment (Stage 2 Claude) is the sole per-question severity
            source.

        Degraded mode safety net (Stage 2 LLM both providers failed):
          - If Stage 1c keyword matched, escalate to HIGH so the crisis
            signal is preserved.
          - Otherwise: NONE (LLM unavailable, no fallback signal).
        """
        if self.assessment:
            return self.assessment.severity

        if self.degraded_mode and self.keyword_result and self.keyword_result.matched:
            return Severity.HIGH

        return Severity.NONE


class SurveyAssessmentResult(BaseModel):
    """Survey-level pipeline output."""
    rule_result: RuleResult
    per_question: list[QuestionAssessment]
    final_severity: Severity
    flagged: bool
    inference_mode: str  # 'full' or 'rule_only'
    pipeline_latency_ms: int


def validate_evidence_phrases(source_text: str, phrases: list[str]) -> list[str]:
    lowered = source_text.lower()
    return [p for p in phrases if p.lower() in lowered]
