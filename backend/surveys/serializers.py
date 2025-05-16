from rest_framework import serializers
from .models import SurveyResponse, FlaggedStudent, Student

class SurveyResponseSerializer(serializers.ModelSerializer):
    """
    SurveyResponseSerializer helps in converting strings to JSON objects
    and vice-versa.
    """
    class Meta:
        model = SurveyResponse
        fields = "__all__"


class FlaggedStudentSerializer(serializers.ModelSerializer):
    """
    FlaggedStudentSerializer helps in converting strings to JSON objects
    and vice-versa.
    """
    student_response = serializers.PrimaryKeyRelatedField(queryset=SurveyResponse.objects.all())
    class Meta:
        model = FlaggedStudent
        fields = "__all__"


class StudentSerializer(serializers.ModelSerializer):
    """
    StudentSerializer helps in converting strings to JSON objects
    and vice-versa.
    """
    class Meta:
        model = Student
        fields = "__all__"