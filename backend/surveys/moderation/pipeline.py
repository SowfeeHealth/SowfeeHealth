"""Moderation pipeline orchestrator.

Survey-level pipeline:
- Stage 1a: rule engine (1x per survey, Likert-based).
- Per text question (parallel, Semaphore-bounded):
    Stage 0: PII redaction
    Stage 1b: Llama Guard classifier (skipped in rule_only mode)
    Stage 1c: keyword filter (always)
    Stage 2: LLM assessment (only if triggered; skipped in rule_only mode)

Stage 2 input is strictly text + question_text — no Likert, no rule scores.
"""
import asyncio
import logging
import time

from .backends.base import (
    AssessmentContext,
    BackendInvalidOutput,
    BackendUnavailable,
    ClassifierContext,
)
from .keyword_filter import check_keywords
from .redaction import redact_pii
from .rules import compute_rule_scores
from .schemas import (
    LikertResponse,
    QuestionAssessment,
    SEVERITY_ORDER,
    Severity,
    SurveyAssessmentResult,
)


logger = logging.getLogger(__name__)

MAX_CONCURRENT_PIPELINES = 5


class ModerationPipeline:
    """Survey-level moderation pipeline.

    Stage 1a: rule engine, 1x per survey (Likert-based).
    Per-question (parallel, Semaphore-bounded):
      Stage 0: PII redaction
      Stage 1b: Llama Guard classifier (skipped in rule_only)
      Stage 1c: keyword filter (always)
      Stage 2: LLM assessment (only if triggered; skipped in rule_only)

    Stage 2 input: text + question_text only. No Likert, no rule scores.
    """

    def __init__(self, classifier, assessor, rules=None):
        self._classifier = classifier
        self._assessor = assessor
        self._rules = rules or []

    async def process_survey(
        self,
        text_responses: list[tuple[int, str, str]],
        likert_responses: list[LikertResponse],
        inference_mode: str = "full",
    ) -> SurveyAssessmentResult:
        """Process entire survey.

        Args:
            text_responses: List of (question_id, raw_text, question_text).
            likert_responses: Student's Likert answers for Stage 1a.
            inference_mode: 'full' or 'rule_only'.
        """
        t_start = time.monotonic()

        # Stage 1a: rule engine (1x per survey)
        rule_result = compute_rule_scores(likert_responses, self._rules)
        rule_flagged = rule_result.flagged

        # Per-question parallel
        sem = asyncio.Semaphore(MAX_CONCURRENT_PIPELINES)
        per_question = await asyncio.gather(*[
            self._process_question(
                qid, text, qtext,
                inference_mode, rule_flagged, sem,
            )
            for qid, text, qtext in text_responses
        ])

        # Aggregate final_severity = max(rule, all per_question)
        sevs = [rule_result.suggested_severity if rule_flagged else Severity.NONE]
        for q in per_question:
            sevs.append(q.severity_max())
        final_severity = max(sevs, key=lambda s: SEVERITY_ORDER[s])
        flagged = final_severity != Severity.NONE

        latency_ms = int((time.monotonic() - t_start) * 1000)

        return SurveyAssessmentResult(
            rule_result=rule_result,
            per_question=per_question,
            final_severity=final_severity,
            flagged=flagged,
            inference_mode=inference_mode,
            pipeline_latency_ms=latency_ms,
        )

    async def _process_question(
        self,
        question_id: int,
        text: str,
        question_text: str,
        inference_mode: str,
        survey_rule_flagged: bool,
        sem: asyncio.Semaphore,
    ) -> QuestionAssessment:
        """Process single text question."""
        async with sem:
            # Stage 0
            try:
                redacted, _audit_log = await redact_pii(text)
            except ValueError as exc:
                logger.warning("Stage 0 failed Q%d: %s", question_id, exc)
                return QuestionAssessment(
                    question_id=question_id,
                    redacted_text=text,
                    keyword_result=None,
                    classifier_result=None,
                    assessment=None,
                    degraded_mode=True,
                    degraded_reason=f"Stage 0 failed: {exc}",
                )

            # Stage 1c
            keyword_result = check_keywords(redacted)

            # rule_only mode: skip 1b + 2
            if inference_mode == "rule_only":
                return QuestionAssessment(
                    question_id=question_id,
                    redacted_text=redacted,
                    keyword_result=keyword_result,
                    classifier_result=None,
                    assessment=None,
                )

            # Stage 1b
            classifier_result = None
            classifier_context: ClassifierContext = {}
            if question_text:
                classifier_context["question_text"] = question_text
            try:
                classifier_result = await self._classifier.classify(
                    redacted, classifier_context
                )
            except (BackendUnavailable, BackendInvalidOutput) as exc:
                logger.warning("Stage 1b failed Q%d: %s", question_id, exc)

            # Stage 2 trigger
            stage2_needed = (
                survey_rule_flagged
                or keyword_result.matched
                or (classifier_result is not None and classifier_result.flagged)
            )

            # Stage 2
            assessment = None
            degraded = False
            degraded_reason = None

            if stage2_needed:
                ctx: AssessmentContext = {
                    "question_text": question_text,
                }
                try:
                    assessment = await self._assessor.assess(redacted, ctx)
                except BackendUnavailable as exc:
                    logger.error("Stage 2 unavailable Q%d: %s", question_id, exc)
                    degraded = True
                    degraded_reason = f"Stage 2 unavailable: {exc}"
                except BackendInvalidOutput as exc:
                    logger.error("Stage 2 invalid output Q%d: %s", question_id, exc)
                    degraded = True
                    degraded_reason = f"Stage 2 invalid output: {exc}"

            return QuestionAssessment(
                question_id=question_id,
                redacted_text=redacted,
                keyword_result=keyword_result,
                classifier_result=classifier_result,
                assessment=assessment,
                degraded_mode=degraded,
                degraded_reason=degraded_reason,
            )
