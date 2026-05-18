"""Moderation pipeline orchestrator.

Survey-level pipeline:
- Stage 1a: rule engine (1x per survey, Likert-based).
- Per text question (parallel, Semaphore-bounded):
    Stage 0: PII redaction (Microsoft Presidio)
    Stage 1c: keyword filter (audit + degraded-mode safety net ONLY)
    Stage 2: Claude assessment (sole content classifier; ALWAYS runs in
             'full' mode; skipped in rule_only mode)

Stage 1b (Llama Guard) was removed from the pipeline flow because it
cannot detect implicit distress signals outside the MLCommons hazard
taxonomy (academic failure, self-deprecation, social isolation) — a
model knowledge gap, not a prompt/threshold tuning problem.
backends/together.py is preserved as deprecated for reference; it is
no longer imported from this module.

Stage 1c (keyword filter) is kept but downgraded to audit + safety net:
its matches are recorded on QuestionAssessment for audit, and only
contribute to severity_max() when Stage 2 LLM both providers fail
(degraded_mode). See severity_max() in schemas.py.

Stage 2 input is strictly text + question_text — no Likert, no rule scores.
"""
import asyncio
import logging
import time

from .backends.base import (
    AssessmentContext,
    BackendInvalidOutput,
    BackendUnavailable,
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
      Stage 1c: keyword filter (audit + degraded-mode safety net only)
      Stage 2: Claude assessment (sole content classifier; ALWAYS runs
               in 'full' mode; skipped in rule_only)

    Stage 1b (Llama Guard) is no longer in the pipeline flow — Stage 2
    Claude is the sole content severity judge. Stage 1c contributes to
    severity only when Stage 2 fails (both providers unavailable).

    Stage 2 input: text + question_text only. No Likert, no rule scores.
    """

    def __init__(self, assessor, rules=None):
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
                inference_mode, sem,
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
                    assessment=None,
                    degraded_mode=True,
                    degraded_reason=f"Stage 0 failed: {exc}",
                )

            # Stage 1c — audit + degraded-mode safety net only
            keyword_result = check_keywords(redacted)

            # rule_only mode: skip Stage 2 entirely (no LLM call)
            if inference_mode == "rule_only":
                return QuestionAssessment(
                    question_id=question_id,
                    redacted_text=redacted,
                    keyword_result=keyword_result,
                    assessment=None,
                )

            # Stage 2 — sole content classifier; ALWAYS runs in 'full' mode.
            # No trigger gate: Llama Guard removed because its training data
            # misses implicit distress signals. Claude evaluates every text.
            assessment = None
            degraded = False
            degraded_reason = None

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
                assessment=assessment,
                degraded_mode=degraded,
                degraded_reason=degraded_reason,
            )
