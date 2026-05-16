import asyncio
import logging

from celery import shared_task
from django_tenants.utils import get_tenant_model, tenant_context

from .moderation.backends.factory import get_pipeline
from .moderation.schemas import (
    FlaggingRule,
    LikertResponse,
    LikertSummary,
    Severity,
)
from .models import QuestionResponse, SurveyQuestion, SurveyResponse


logger = logging.getLogger(__name__)


# Maximum concurrent LLM pipelines per task invocation. Prevents burst
# API token usage or rate limit overflow when a survey has many open-ended
# text questions. Tune based on API tier and observed latency in Phase 9.
MAX_CONCURRENT_PIPELINES = 5


async def _run_pipelines_concurrent(
    pipeline,
    text_responses,
    likert_responses_list,
    question_text_map,
    likert_summary,
):
    """Run pipeline on all text responses concurrently in single event loop.

    Concurrency is bounded by MAX_CONCURRENT_PIPELINES via asyncio.Semaphore.
    This prevents burst LLM API calls when a survey contains many open-ended
    text questions. Single event loop keeps SDK connection pool reusable.

    Returns list of (question_id, PipelineResult) tuples.
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_PIPELINES)

    async def _bounded_process(qid, text):
        async with semaphore:
            result = await pipeline.process(
                text=text,
                likert_responses=likert_responses_list,
                question_text=question_text_map.get(qid),
                likert_summary=likert_summary,
            )
            return qid, result

    tasks = [_bounded_process(qid, text) for qid, text in text_responses]
    return await asyncio.gather(*tasks)


@shared_task
def analyze_survey_responses_async(survey_response_id, question_ids, schema_name):
    """Run moderation pipeline on a survey response.

    Triggered from surveys/survey_views.py via transaction.on_commit.
    Updates survey_response.flagged based on pipeline output.
    """
    Tenant = get_tenant_model()
    try:
        tenant = Tenant.objects.get(schema_name=schema_name)
    except Tenant.DoesNotExist:
        logger.error("Tenant not found: %s", schema_name)
        return

    with tenant_context(tenant):
        try:
            survey_response = SurveyResponse.objects.get(id=survey_response_id)
        except SurveyResponse.DoesNotExist:
            logger.error("SurveyResponse not found: %s", survey_response_id)
            return

        likert_responses_list = []
        text_responses = []
        question_text_map = {}

        for question_id in question_ids:
            try:
                qresp = QuestionResponse.objects.select_related('question').get(
                    survey_response=survey_response, question_id=question_id
                )
            except QuestionResponse.DoesNotExist:
                continue

            question = qresp.question
            question_text_map[question.id] = question.question_text

            if qresp.likert_value is not None:
                choices = question.answer_choices or SurveyQuestion.DEFAULT_LIKERT_CHOICES
                likert_responses_list.append(LikertResponse(
                    question=question.question_text,
                    answer_choices=choices,
                    category=question.category or "general",
                    answer=qresp.likert_value,
                ))
            elif qresp.text_response:
                text_responses.append((question.id, qresp.text_response))

        # TODO Phase 7: load FlaggingRule from institution config
        rules = [
            FlaggingRule(
                category="depression",
                rule_type="sum",
                threshold=12,
                comparison="gte",
                severity=Severity.HIGH,
                description="High depression score",
            ),
            FlaggingRule(
                category="stress",
                rule_type="average",
                threshold=3,
                comparison="gte",
                severity=Severity.MEDIUM,
                description="High average stress",
            ),
            FlaggingRule(
                category="sleep",
                rule_type="average",
                threshold=2,
                comparison="lte",
                severity=Severity.MEDIUM,
                description="Sleep deprivation",
            ),
        ]
        pipeline = get_pipeline(tenant, rules)
        likert_summary = LikertSummary(scale="Sowfee 4-category")

        any_flagged = False

        if not text_responses:
            result = asyncio.run(pipeline.process(
                text="",
                likert_responses=likert_responses_list,
                question_text=None,
                likert_summary=likert_summary,
            ))
            any_flagged = result.flagged
            logger.info(
                "Pipeline (no text) for survey_response %s: "
                "flagged=%s severity=%s degraded=%s latency=%dms",
                survey_response_id, result.flagged,
                result.final_severity.value, result.degraded_mode,
                result.pipeline_latency_ms,
            )
        else:
            results = asyncio.run(_run_pipelines_concurrent(
                pipeline, text_responses, likert_responses_list,
                question_text_map, likert_summary,
            ))
            any_flagged = any(r.flagged for _, r in results)

            for qid, result in results:
                # TODO Phase 7: save CrisisAssessmentRecord to DB
                logger.info(
                    "Pipeline result for survey_response %s, question %s: "
                    "flagged=%s severity=%s degraded=%s latency=%dms",
                    survey_response_id, qid, result.flagged,
                    result.final_severity.value, result.degraded_mode,
                    result.pipeline_latency_ms,
                )

        survey_response.flagged = any_flagged
        survey_response.save(update_fields=['flagged'])

        logger.info(
            "Moderation complete for survey_response %s: flagged=%s",
            survey_response_id, any_flagged
        )
