from typing import Protocol, TypedDict

from ..schemas import ClassifierResult, CrisisAssessment


class AssessmentContext(TypedDict, total=False):
    """Stage 2 LLM input — text only.

    Excludes Likert data and rule scores by design. Those are Stage 1a's
    responsibility. Stage 2 LLM evaluates student text in isolation;
    clinical context (Likert evaluation) lives in deterministic Stage 1a,
    not in LLM reasoning. Including Likert data risks the LLM hallucinating
    severity from numeric context the rule engine already evaluated.
    """
    question_text: str


class ClassifierContext(TypedDict, total=False):
    """Context for Stage 1b classifier (Llama Guard).
    
    Currently only needs question_text for Q&A conversation format —
    catches single-word answers like 'Yes' to clinical questions.
    """
    question_text: str


class ClassifierBackend(Protocol):
    """Stage 1b: takes redacted text + context, returns ClassifierResult.

    context dict recognised keys (all optional):
      question_text (str): original question the student answered
    """

    async def classify(
        self,
        text: str,
        context: ClassifierContext,
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
