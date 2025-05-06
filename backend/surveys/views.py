from django.shortcuts import render, redirect
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.parsers import JSONParser
#from django.views.decorators.csrf import csrf_exempt
from .models import SurveyResponse, FlaggedStudents, Student, User
from .serializers import SurveyResponseSerializer, FlaggedStudentsSerializer, StudentSerializer
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.urls import reverse
from .forms import SurveyForm
from django.contrib import messages

@api_view(["GET"])
def index_view(request):
    return render(request, 'index.html')

@api_view(["GET", "POST"])
def survey_view(request):
    if request.method == 'GET':
        return render(request, 'survey.html')  # Render form if it's a GET request
    elif request.method == 'POST':
        required_fields = ['student_name', 'school_email', 'q1', 'q2', 'q3', 'q4', 'q5']
        missing_fields = [field for field in required_fields if field not in request.POST]

        if missing_fields:
            return JsonResponse({"success": False, "error": f"Missing fields: {', '.join(missing_fields)}"})

        # Call handleStudentResponses directly with request.POST as data
        return student_response_view(request)

@api_view(['GET', 'POST'])
def student_response_view(request):
    
    if request.method == "GET":
        surveyResponses = SurveyResponse.objects.all()
        serializer = SurveyResponseSerializer(surveyResponses, many=True)
        return Response(serializer.data)

    elif request.method == "POST":

        # Save responses and check if student should be flagged
        student_name = request.POST.get('student_name')
        school_email = request.POST.get('school_email')
        university_id = school_email.split('@')[1].split('.')[0] if '@' in school_email else 'Unknown'
        #university_id = Student.objects.filter(student_name=student_name, school_email=school_email).first().university_id
        serializer_data = {"student_name": request.POST["student_name"], 
                           "school_email": request.POST["school_email"],
                           "university_id": university_id,
                           "q1": request.POST["q1"],
                           "q2": request.POST["q2"],
                           "q3": request.POST["q3"],
                           "q4": request.POST["q4"],
                           "q5": request.POST["q5"]}

        # Delete any existing response for the same student
        SurveyResponse.objects.filter(student_name=student_name, school_email=school_email).delete()

        serializer = SurveyResponseSerializer(data=serializer_data)
        if serializer.is_valid():

            survey_result = serializer.save()  # This will always create a new response

            '''
            # Process student data
            student_data = {
                "school_email": survey_result.school_email,
                "student_name": survey_result.student_name,  # university_id will be auto-generated
                "university_id": university_id
            }
            students_serializer = StudentSerializer(data=student_data)
            if students_serializer.is_valid():
                students_serializer.save()
                print("Student data", students_serializer.data, flush=True)
            else:
                print("Error saving student:", students_serializer.errors, flush=True)
            '''
            # Check if student should be flagged
            if any(getattr(survey_result, f'q{i}') >= 3 for i in range(1, 6)):
                flagged_data = {
                    "school_email": survey_result.school_email,
                    "student_name": survey_result.student_name,
                    "student_response": survey_result.school_email,
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
def flagged_students_view(request):
    if request.method == "GET":
        flaggedStudents = FlaggedStudents.objects.all()
        flaggedStudentsSerializer = FlaggedStudentsSerializer(flaggedStudents, many=True)
        return Response(flaggedStudentsSerializer.data)

@api_view(["GET"])
def students_view(request):
    if request.method == "GET":
        all_students = Student.objects.all()
        students_serializer = StudentSerializer(all_students, many=True)
        return Response(students_serializer.data)
    else:
        return HttpResponse(status=501)

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
                                              "response_rate": int(total_responses/total_students * 100) if total_students > 0 else 0})

def login_view(request):
    if request.method == "POST":
        email = request.POST['email']
        password = request.POST['password']
        # Extract university_id from the email
        university_id = email.split('@')[1].split('.')[0] if '@' in email else 'Unknown'
        user = authenticate(request, email=email, password=password)
        if user is not None:
            login(request, user)  # Creates a session for the user
            messages.success(request, "Login Successful!")
            # Check if university_id exists in the Student database
            if Student.objects.filter(university_id=university_id).exists():
                # Redirect to the 'dashboard' if university_id exists
                return redirect(reverse('dashboard', kwargs={'university': university_id}))
            else:
                # Redirect to the 'index' if university_id does not exist
                return redirect('index')  # Change 'index' to the actual URL name if it's different
        else:
            messages.error(request, "Invalid username or password")

    return render(request, 'login.html')

def register_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return redirect("register")

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
            return redirect("register")

        # Create a new user
        user = User.objects.create_user(email=email, password=password)
        user.save()
        messages.success(request, "Registration successful! Please log in.")
        return redirect("login")  # Redirect to login page
    return render(request, "register.html")

