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
