from rest_framework import serializers
from .models import SurveyResponse, FlaggedStudents

class SurveyResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyResponse
        fields = "__all__"

class FlaggedStudentsSerializer(serializers.ModelSerializer):
    class Meta:
        model = FlaggedStudents
        fields = "__all__"