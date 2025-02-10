from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.decorators import api_view
from .models import SurveyResponse
from .serializers import SurveyResponseSerializer
from django.http import JsonResponse


@api_view(['GET', 'POST'])
def handleStudentResponses(request):
    if request.method == "GET":
        surveyResponses = SurveyResponse.objects.all()
        serializer = SurveyResponseSerializer(surveyResponses, many=True)
        return Response(serializer.data)

    elif request.method == "POST":
        serializer = SurveyResponseSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
        return JsonResponse(request.data)