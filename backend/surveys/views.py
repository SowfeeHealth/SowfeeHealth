from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.decorators import api_view
from .models import SurveyResponse, FlaggedStudents
from .serializers import SurveyResponseSerializer, FlaggedStudentsSerializer
from django.http import JsonResponse


@api_view(['GET', 'POST'])
def handleStudentResponses(request):
    if request.method == "GET":
        # Get all student responses
        surveyResponses = SurveyResponse.objects.all()
        serializer = SurveyResponseSerializer(surveyResponses, many=True)
        return Response(serializer.data)

    elif request.method == "POST":
        # Save responses and check if student should be flagged
        serializer = SurveyResponseSerializer(data=request.data)
        if serializer.is_valid():
            # Save student response
            serializer.save()

            # Check if student should be flagged
            flagged = False
            studentResponses = serializer.data
            if studentResponses["q1"] == 1:
                flagged = True
            elif studentResponses["q2"] == 5:
                flagged = True
            elif studentResponses["q3"] == 1:
                flagged = True
            elif studentResponses["q4"] == 1:
                flagged = True
            elif studentResponses["q5"] == 1:
                flagged = True
            if flagged:
                flaggedResponseData = {
                                       "school_email": studentResponses["school_email"],
                                       "student_name": studentResponses["student_name"],
                                       "student_response": studentResponses["id"]
                                       }
                flaggedResponseSerializer = FlaggedStudentsSerializer(data=flaggedResponseData)
                if flaggedResponseSerializer.is_valid():
                    flaggedResponseSerializer.save()

        return JsonResponse(request.data)


@api_view(["GET"])
def handleFlaggedStudents(request):
    if request.method == "GET":
        # Get all the flagged students
        flaggedStudents = FlaggedStudents.objects.all()
        flaggedStudentsSerializer = FlaggedStudentsSerializer(flaggedStudents, many=True)
        return Response(flaggedStudentsSerializer.data)