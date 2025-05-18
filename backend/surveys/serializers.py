from rest_framework import serializers
from .models import SurveyResponse, User, Institution

class SurveyResponseSerializer(serializers.ModelSerializer):
    """
    SurveyResponseSerializer helps in converting strings to JSON objects
    and vice-versa.
    """
    student = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    class Meta:
        model = SurveyResponse
        fields = "__all__"


class UserSerializer(serializers.ModelSerializer):
    """
    UserSerializer helps in converting strings to JSON objects
    and vice-versa.
    """
    institution_details = serializers.PrimaryKeyRelatedField(queryset=Institution.objects.all())
    class Meta:
        model = User
        fields = "__all__"


class InstitutionSerializer(serializers.ModelSerializer):
    """
    InstitutionSerializer helps in converting strings to JSON objects
    and vice-versa.
    """
    class Meta:
        model = Institution
        fields = "__all__"