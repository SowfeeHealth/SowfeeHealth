from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.decorators import api_view
from .models import SurveyResponse, FlaggedStudents
from students.models import Student
from .serializers import SurveyResponseSerializer, FlaggedStudentsSerializer
from django.http import JsonResponse


@api_view(["GET"])
def index_view(request):
    return render(request, 'index.html')


@api_view(["GET", "POST"])
def survey_view(request):
    if request.method == 'GET':
        return render(request, 'survey.html')  # Render form if it's a GET request
    
    elif request.method == 'POST':

        # Check for missing fields
        required_fields = ['student_name', 'school_email', 'q1', 'q2', 'q3', 'q4', 'q5']
        missing_fields = [field for field in required_fields if field not in request.POST]

        if missing_fields:
            return JsonResponse({"success": False, "error": f"Missing fields: {', '.join(missing_fields)}"})

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
        university_id = Student.objects.filter(student_name=student_name, student_email=school_email).first().university_id
        serializer_data = {"student_name": request.data["student_name"], 
                           "school_email": request.data["school_email"],
                           "university_id": university_id,
                           "q1": request.data["q1"],
                           "q2": request.data["q2"],
                           "q3": request.data["q3"],
                           "q4": request.data["q4"],
                           "q5": request.data["q5"]}

        # Delete any existing response for the same student
        SurveyResponse.objects.filter(student_name=student_name, school_email=school_email).delete()

        serializer = SurveyResponseSerializer(data=serializer_data)
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

            # Return success response
            response_data = {
                "success": True,
                "message": "Thank you for your honest response! Your input makes a difference.",
                "data": serializer.data  
            }
            return JsonResponse(response_data)
        
        else:

            # Return error response
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


@api_view(["GET"])
def dashboard_view(request, university):

    total_students = len(Student.objects.filter(university_id = university))

    all_flagged_students = FlaggedStudents.objects.all()
    school_flagged_students = []
    for student in all_flagged_students:
        if student.student_response.university_id == university:
            school_flagged_students.append((student.student_name, student.school_email))

    total_flagged_students = len(school_flagged_students)
    all_responses = SurveyResponse.objects.filter(university_id = university)
    total_responses = len(all_responses)

    return render(request, 'dashboard.html', {"total_students": total_students, "flagged_students": school_flagged_students, 
                                              "total_flagged_students": total_flagged_students, "total_responses": total_responses,
                                              "response_rate": int(total_responses/total_students * 100)})