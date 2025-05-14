from rest_framework import serializers
from .models import SurveyResponse, FlaggedStudents, Student

class SurveyResponseSerializer(serializers.ModelSerializer):
    """
    SurveyResponseSerializer helps in converting strings to JSON objects
    and vice-versa.
    """
    class Meta:
        model = SurveyResponse
        fields = "__all__"


class FlaggedStudentsSerializer(serializers.ModelSerializer):
    """
    FlaggedStudentsSerializer helps in converting strings to JSON objects
    and vice-versa.
    """
    student_response = serializers.PrimaryKeyRelatedField(queryset=SurveyResponse.objects.all())
    class Meta:
        model = FlaggedStudents
        fields = "__all__"


class StudentSerializer(serializers.ModelSerializer):
    """
    StudentSerializer helps in converting strings to JSON objects
    and vice-versa.
    """
    class Meta:
        model = Student
        fields = "__all__"