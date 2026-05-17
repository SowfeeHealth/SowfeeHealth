import asyncio
import logging

from celery import shared_task
from django.db import transaction
from django_tenants.utils import get_tenant_model, tenant_context

from .moderation.backends.factory import get_pipeline
from .moderation.schemas import LikertResponse
from .models import (
    CrisisAssessmentRecord,
    FlaggingRule,
    QuestionResponse,
    SurveyQuestion,
    SurveyResponse,
)


logger = logging.getLogger(__name__)


@shared_task
def analyze_survey_responses_async(survey_response_id, question_ids, schema_name):
    """Run moderation pipeline on a survey response."""
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

        for question_id in question_ids:
            try:
                qresp = QuestionResponse.objects.select_related('question').get(
                    survey_response=survey_response, question_id=question_id
                )
            except QuestionResponse.DoesNotExist:
                continue

            question = qresp.question

            if qresp.likert_value is not None:
                choices = question.answer_choices or SurveyQuestion.DEFAULT_LIKERT_CHOICES
                likert_responses_list.append(LikertResponse(
                    question=question.question_text,
                    answer_choices=choices,
                    category=question.category or "general",
                    answer=qresp.likert_value,
                ))
            elif qresp.text_response:
                text_responses.append(
                    (question.id, qresp.text_response, question.question_text)
                )

        rules = [r.to_pydantic() for r in FlaggingRule.objects.filter(enabled=True)]
        pipeline = get_pipeline(tenant, rules)

        inference_mode = tenant.inference_mode

        # Pipeline call is OUTSIDE atomic block — LLM API calls take seconds;
        # holding a DB transaction that long is wrong.
        result = asyncio.run(pipeline.process_survey(
            text_responses=text_responses,
            likert_responses=likert_responses_list,
            inference_mode=inference_mode,
        ))

        # Atomic: per-question records + SurveyResponse update must succeed
        # or rollback together. Prevents partial-write inconsistency.
        with transaction.atomic():
            for q_assessment in result.per_question:
                CrisisAssessmentRecord.from_question_assessment(
                    survey_response, q_assessment
                )

            survey_response.flagged = result.flagged
            survey_response.final_severity = result.final_severity.value
            survey_response.pipeline_latency_ms = result.pipeline_latency_ms
            survey_response.inference_mode_used = result.inference_mode
            survey_response.save(update_fields=[
                'flagged',
                'final_severity',
                'pipeline_latency_ms',
                'inference_mode_used',
            ])
            # save() override auto-adds final_severity_order to update_fields

        # Log AFTER atomic commit. If atomic block raises, exception
        # propagates to Celery; log doesn't fire.
        logger.info(
            "Pipeline complete for SR#%s: severity=%s flagged=%s "
            "mode=%s latency=%dms questions=%d",
            survey_response_id,
            result.final_severity.value,
            result.flagged,
            result.inference_mode,
            result.pipeline_latency_ms,
            len(result.per_question),
        )
