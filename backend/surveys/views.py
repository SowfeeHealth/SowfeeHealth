from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.parsers import JSONParser
#from django.views.decorators.csrf import csrf_exempt
from .models import SurveyResponse, FlaggedStudents
from .serializers import SurveyResponseSerializer, FlaggedStudentsSerializer
from django.http import JsonResponse

from .forms import SurveyForm
from django.contrib import messages

def index_view(request):
    return render(request, 'index.html')

#@csrf_exempt
def survey_view(request):
    if request.method == 'GET':
        return render(request, 'survey.html')  # Render form if it's a GET request
    elif request.method == 'POST':
        print("POST Data:", request.POST)

        required_fields = ['student_name', 'school_email', 'q1', 'q2', 'q3', 'q4', 'q5']
        missing_fields = [field for field in required_fields if field not in request.POST]

        if missing_fields:
            print(f"Missing fields: {missing_fields}")
            return JsonResponse({"success": False, "error": f"Missing fields: {', '.join(missing_fields)}"})

        # Call handleStudentResponses directly with request.POST as data
        return handleStudentResponses(request)

@api_view(['GET', 'POST'])
def handleStudentResponses(request):
    if request.method == "GET":
        # Get all student responses
        surveyResponses = SurveyResponse.objects.all()
        serializer = SurveyResponseSerializer(surveyResponses, many=True)
        return Response(serializer.data)

    elif request.method == "POST":
        # Save responses and check if student should be flagged
        student_name = request.data.get('student_name')
        school_email = request.data.get('school_email')

        # Delete any existing response for the same student
        SurveyResponse.objects.filter(student_name=student_name, school_email=school_email).delete()

        serializer = SurveyResponseSerializer(data=request.data)
        if serializer.is_valid():

            survey_result = serializer.save()  # This will always create a new response

            # Check if student should be flagged
            if any(getattr(survey_result, f'q{i}') >= 3 for i in range(1, 6)):
                flagged_data = {
                    "school_email": survey_result.school_email,
                    "student_name": survey_result.student_name,
                    "student_response": survey_result.id
                }
                # Delete any existing response for the same student
                FlaggedStudents.objects.filter(student_name=student_name, school_email=school_email).delete()
                flagged_serializer = FlaggedStudentsSerializer(data=flagged_data)
                if flagged_serializer.is_valid():
                    flagged_serializer.save()
                    response_data = {
                    "success": True,
                    "message": "Thank you for your honest response! Your input makes a difference.",
                    "data": flagged_serializer.data  
                    }
                    return JsonResponse(response_data)
                else:
                    console.log("error occured serializing")
            else:
                response_data = {
                    "success": True,
                    "message": "Thank you for your honest response! Your input makes a difference.",
                    "data": serializer.data  
                }
                return JsonResponse(response_data)
        else:
            print(f"Serializer Errors: {serializer.errors}")
            return JsonResponse({
                "success": False,
                "message": "There was an error with your submission.",
                "data": serializer.errors
            })


@api_view(["GET"])
def handleFlaggedStudents(request):
    if request.method == "GET":
        # Get all the flagged students
        flaggedStudents = FlaggedStudents.objects.all()
        flaggedStudentsSerializer = FlaggedStudentsSerializer(flaggedStudents, many=True)
        return Response(flaggedStudentsSerializer.data)

def dashboard_view(request):
    return render(request, 'dashboard.html')  # Pass data to template
