from celery import shared_task
from .llm_services import analyze_mental_health_responses
from .models import SurveyResponse, QuestionResponse, SurveyQuestion


@shared_task
def analyze_survey_responses_async(response_id, question_ids):
    """Analyze survey answers and update flag in database"""
    try:
        for question_id in question_ids:
            question = SurveyQuestion.objects.get(id=question_id)
            question_response = QuestionResponse.objects.filter(
                survey_response_id=response_id,
                question=question
            ).first()
            if question_response and question_response.text_response:
                question_text = question.question_text
                result = analyze_mental_health_responses(
                    text=question_response.text_response,
                    question_text=question_text
                )
                if result['flag'] and result['severity'] in ['high', 'medium']:
                    SurveyResponse.objects.filter(id=response_id).update(
                        flagged=True,
                    )
                    return f"Response {response_id} flagged: {result['reason']}"
        return f"Response {response_id} analyzed - no concerns"
    except Exception as e:
        print(f"Error analyzing response {response_id}: {str(e)}")
        return f"Error: {str(e)}"

