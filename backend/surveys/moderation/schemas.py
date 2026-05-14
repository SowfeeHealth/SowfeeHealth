from enum import Enum

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
