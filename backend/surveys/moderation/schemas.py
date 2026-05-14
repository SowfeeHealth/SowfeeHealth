from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Severity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class HazardCategory(str, Enum):
    VIOLENT_CRIMES = "S1"
    NON_VIOLENT_CRIMES = "S2"
    SEX_CRIMES = "S3"
    CHILD_SEXUAL_EXPLOITATION = "S4"
    DEFAMATION = "S5"
    SPECIALIZED_ADVICE = "S6"
    PRIVACY = "S7"
    INTELLECTUAL_PROPERTY = "S8"
    INDISCRIMINATE_WEAPONS = "S9"
    HATE = "S10"
    SUICIDE_SELF_HARM = "S11"
    SEXUAL_CONTENT = "S12"
    ELECTIONS = "S13"
    CODE_INTERPRETER_ABUSE = "S14"


class ClassifierResult(BaseModel):
    flagged: bool
    categories: list[HazardCategory]
    confidence: float = Field(ge=0.0, le=1.0)
    raw_output: str
    latency_ms: int
    provider: str


class RuleResult(BaseModel):
    flagged: bool
    triggers: list[str]
    category_scores: dict[str, int]
    severity: Severity
    latency_ms: int


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


class TierAssignment(BaseModel):
    tier: int = Field(ge=1, le=3)
    urgency_window: str
    notification_channels: list[str]
    reasoning: str


def validate_evidence_phrases(source_text: str, phrases: list[str]) -> list[str]:
    lowered = source_text.lower()
    return [p for p in phrases if p.lower() in lowered]
