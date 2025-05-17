from rest_framework import serializers
from .models import SurveyResponse, User

class SurveyResponseSerializer(serializers.ModelSerializer):
    """
    SurveyResponseSerializer helps in converting strings to JSON objects
    and vice-versa.
    """
    class Meta:
        model = SurveyResponse
        fields = "__all__"


class UserSerializer(serializers.ModelSerializer):
    """
    UserSerializer helps in converting strings to JSON objects
    and vice-versa.
    """
    class Meta:
        model = User
        fields = "__all__"