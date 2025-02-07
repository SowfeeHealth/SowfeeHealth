from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.decorators import api_view
from .models import SurveyResponse
from .serializers import SurveyResponseSerializer


@api_view(['GET'])
def getStudentResponses(request):
    surveyResponses = SurveyResponse.objects.all()
    serializer = SurveyResponseSerializer(surveyResponses, many=True)
    return Response(serializer)