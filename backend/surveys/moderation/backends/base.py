from typing import Protocol, TypedDict

from ..schemas import ClassifierResult, CrisisAssessment


class AssessmentContext(TypedDict, total=False):
    rule_scores: dict[str, int]
    question_text: str
    likert_summary: dict[str, object]


class ClassifierBackend(Protocol):
    """Stage 1b: takes redacted text + context, returns ClassifierResult.

    context dict recognised keys (all optional):
      question_text (str): original question the student answered
      rule_scores (dict[str, int]): category_scores from Stage 1a
      likert_summary (dict): Likert score summary
    """

    async def classify(
        self,
        text: str,
        context: AssessmentContext,
    ) -> ClassifierResult: ...


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

    Raised for:
    - AssessmentBackend: Pydantic schema mismatch, evidence_phrase not
      found verbatim in source text after one retry with stronger prompt.
    - ClassifierBackend: model returned output that doesn't match the
      expected 'safe' / 'unsafe\\nCategories' format.

    Not retryable in pipeline (data issue, not transient).
    """
