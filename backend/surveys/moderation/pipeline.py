"""Moderation pipeline orchestrator.

Coordinates 4-stage moderation flow:
- Stage 0: PII redaction (synchronous, fail-loud on non-English)
- Stage 1a/b/c: Rule engine + LLM classifier + keyword filter
- Stage 2: LLM clinical assessment (only if any Stage 1 flagged)

Returns PipelineResult with all stage outputs + final decision.
Tenant-agnostic: receives pre-constructed backends from factory.
"""
import logging
import time

from .backends.base import (
    AssessmentBackend,
    AssessmentContext,
    BackendInvalidOutput,
    BackendUnavailable,
    ClassifierBackend,
    ClassifierContext,
)
from .keyword_filter import check_keywords
from .redaction import redact_pii
from .rules import compute_rule_scores
from .schemas import (
    CrisisAssessment,
    FlaggingRule,
    LikertResponse,
    LikertSummary,
    PipelineResult,
    Severity,
)


logger = logging.getLogger(__name__)


class ModerationPipeline:
    """4-stage moderation pipeline.

    Stages run: Stage 0 → Stage 1 (a/b/c) → Stage 2 (conditional).
    Stage 2 triggers only if any Stage 1 component flags.
    """

    def __init__(
        self,
        classifier: ClassifierBackend,
        assessor: AssessmentBackend,
        rules: list[FlaggingRule],
    ) -> None:
        self._classifier = classifier
        self._assessor = assessor
        self._rules = rules

    async def process(
        self,
        text: str,
        likert_responses: list[LikertResponse],
        question_text: str | None = None,
        likert_summary: LikertSummary | None = None,
    ) -> PipelineResult:
        """Run full moderation pipeline on a survey response.

        Args:
            text: Student's free-text response.
            likert_responses: Student's Likert answers (may be empty).
            question_text: The question being answered (Stage 2 context).
            likert_summary: Institution's Likert instrument name (e.g. 'PHQ-9')
                for Stage 2 LLM clinical priming. Optional.

        Returns:
            PipelineResult with all stage outputs + final decision.
        """
        t_start = time.monotonic()

        try:
            redacted_text, _audit_log = await redact_pii(text)
        except ValueError as exc:
            logger.warning("Stage 0 redaction failed: %s", exc)
            return self._degraded_result(
                redacted_text=text,
                redaction_succeeded=False,
                degraded_reason=f"Stage 0 failed: {exc}",
                t_start=t_start,
                likert_responses=likert_responses,
            )

        rule_result = compute_rule_scores(likert_responses, self._rules)
        keyword_result = check_keywords(redacted_text)

        classifier_context: ClassifierContext = {}
        if question_text:
            classifier_context["question_text"] = question_text

        classifier_result = None
        try:
            classifier_result = await self._classifier.classify(
                redacted_text, classifier_context
            )
        except BackendUnavailable as exc:
            logger.warning("Stage 1b classifier unavailable: %s", exc)
        except BackendInvalidOutput as exc:
            logger.warning("Stage 1b classifier invalid output: %s", exc)

        any_flagged = (
            rule_result.flagged
            or keyword_result.matched
            or (classifier_result is not None and classifier_result.flagged)
        )

        assessment: CrisisAssessment | None = None
        degraded = False
        degraded_reason: str | None = None

        if any_flagged:
            assessment_context: AssessmentContext = {}
            if question_text:
                assessment_context["question_text"] = question_text
            if rule_result.category_scores:
                assessment_context["rule_scores"] = rule_result.category_scores
            if likert_responses:
                assessment_context["likert_responses"] = likert_responses
            if likert_summary:
                assessment_context["likert_summary"] = likert_summary

            try:
                assessment = await self._assessor.assess(
                    redacted_text, assessment_context
                )
            except BackendUnavailable as exc:
                logger.error("Stage 2 unavailable (primary+failover): %s", exc)
                degraded = True
                degraded_reason = f"Stage 2 unavailable: {exc}"
            except BackendInvalidOutput as exc:
                logger.error("Stage 2 invalid output: %s", exc)
                degraded = True
                degraded_reason = f"Stage 2 invalid output: {exc}"

        if assessment is not None:
            final_severity = assessment.severity
            flagged = assessment.severity != Severity.NONE
        elif any_flagged:
            final_severity = rule_result.suggested_severity
            flagged = True
        else:
            final_severity = Severity.NONE
            flagged = False

        pipeline_latency_ms = int((time.monotonic() - t_start) * 1000)

        return PipelineResult(
            redacted_text=redacted_text,
            redaction_succeeded=True,
            rule_result=rule_result,
            classifier_result=classifier_result,
            keyword_result=keyword_result,
            assessment=assessment,
            flagged=flagged,
            final_severity=final_severity,
            pipeline_latency_ms=pipeline_latency_ms,
            degraded_mode=degraded,
            degraded_reason=degraded_reason,
        )

    def _degraded_result(
        self,
        redacted_text: str,
        redaction_succeeded: bool,
        degraded_reason: str,
        t_start: float,
        likert_responses: list[LikertResponse],
    ) -> PipelineResult:
        """Build degraded-mode result when Stage 0 fails.

        Stage 1a still runs (doesn't depend on text); others skipped.
        """
        rule_result = compute_rule_scores(likert_responses, self._rules)

        if rule_result.flagged:
            final_severity = rule_result.suggested_severity
            flagged = True
        else:
            final_severity = Severity.NONE
            flagged = False

        pipeline_latency_ms = int((time.monotonic() - t_start) * 1000)

        return PipelineResult(
            redacted_text=redacted_text,
            redaction_succeeded=redaction_succeeded,
            rule_result=rule_result,
            classifier_result=None,
            keyword_result=None,
            assessment=None,
            flagged=flagged,
            final_severity=final_severity,
            pipeline_latency_ms=pipeline_latency_ms,
            degraded_mode=True,
            degraded_reason=degraded_reason,
        )
