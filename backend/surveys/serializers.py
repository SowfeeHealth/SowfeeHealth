
from rest_framework import serializers
from .models import SurveyResponse, User, Institution, SurveyTemplate, SurveyQuestion, QuestionResponse, QuestionType

class SurveyQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyQuestion
        fields = ['id', 'question_text', 'question_type', 'category', 'order']

class QuestionResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionResponse
        fields = ['id', 'question', 'likert_value', 'text_response']

class SurveyResponseSerializer(serializers.ModelSerializer):
    question_responses = QuestionResponseSerializer(many=True, read_only=True)
    
    class Meta:
        model = SurveyResponse
        fields = ['id', 'student', 'survey_template', 'created', 'flagged', 'question_responses']

class SurveyTemplateSerializer(serializers.ModelSerializer):
    questions = SurveyQuestionSerializer(many=True, read_only=True)
    
    class Meta:
        model = SurveyTemplate
        fields = ['id', 'institution', 'hash_link', 'questions']  # removed 'created'

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"

class InstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = "__all__"