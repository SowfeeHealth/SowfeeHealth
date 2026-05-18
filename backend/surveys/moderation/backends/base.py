from typing import Protocol, TypedDict

from ..schemas import CrisisAssessment


class AssessmentContext(TypedDict, total=False):
    """Stage 2 LLM input — text only.

    Excludes Likert data and rule scores by design. Those are Stage 1a's
    responsibility. Stage 2 LLM evaluates student text in isolation;
    clinical context (Likert evaluation) lives in deterministic Stage 1a,
    not in LLM reasoning. Including Likert data risks the LLM hallucinating
    severity from numeric context the rule engine already evaluated.
    """
    question_text: str


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

    Raised for AssessmentBackend: Pydantic schema mismatch, or evidence_phrase
    not found verbatim in source text after one retry with stronger prompt.

    Not retryable in pipeline (data issue, not transient).
    """
