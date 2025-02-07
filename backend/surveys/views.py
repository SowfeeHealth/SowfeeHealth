from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.decorators import api_view
from .models import SurveyResponse
from .serializers import SurveyResponseSerializer


@api_view(['GET'])
def handleStudentResponses(request):
    if request.method == "GET":
        surveyResponses = SurveyResponse.objects.all()
        serializer = SurveyResponseSerializer(surveyResponses, many=True)
        return Response(serializer.data)

    elif request.method == "POST":
        serializer = SurveyResponseSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
        return Response(serializer.data)