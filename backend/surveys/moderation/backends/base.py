from typing import Protocol, TypedDict

from ..schemas import ClassifierResult, CrisisAssessment


class AssessmentContext(TypedDict, total=False):
    rule_scores: dict[str, int]
    question_text: str
    likert_summary: dict[str, object]


class ClassifierBackend(Protocol):
    """Stage 1b: takes redacted text, returns ClassifierResult."""

    async def classify(self, text: str) -> ClassifierResult: ...


class AssessmentBackend(Protocol):
    """Stage 2: takes redacted text + context, returns CrisisAssessment.

    Retries once with a stronger prompt if evidence_phrases cannot be
    grounded in the source text; raises BackendInvalidOutput on second failure.
    """

    async def assess(self, text: str, context: AssessmentContext) -> CrisisAssessment: ...


class BackendError(Exception):
    """Base class for all backend errors."""


class BackendUnavailable(BackendError):
    """Transient error, safe to retry.

    Raised for: network timeout, rate limit, service 5xx.
    Pipeline catches this to apply circuit-breaker / fail-open logic.
    """


class BackendInvalidOutput(BackendError):
    """Backend returned data that failed validation.

    Raised for: Pydantic schema mismatch, evidence_phrase not found verbatim
    in source text after one retry with a stronger prompt.
    Only raised by AssessmentBackend.
    """
