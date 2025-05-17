import logging
import calendar
import re
from .models import SurveyResponse, User
from .serializers import SurveyResponseSerializer, UserSerializer
from django.shortcuts import render, redirect
from django.utils import timezone
from django.http import JsonResponse, HttpResponseBadRequest
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.contrib import messages
from rest_framework.response import Response
from rest_framework.decorators import api_view

# Use a single logger configuration
logger = logging.getLogger("surveys")

@api_view(["GET"])
def index_view(request):
    """
    index_view returns the home page
    """
    if request.method == "GET":
        return render(request, 'index.html')
   

@login_required
@api_view(['GET', 'POST'])
def survey_view(request):
    """
    survey_view allows students to access the survey page
    and save survey responses
    """
    if request.method == 'GET':
        
        # Extract data for the logged in student
        student = User.objects.filter(email=request.COOKIES.get("user_email")).first()
        context = {
            "student_email": student.email,
            "student_name": student.name
        }

        return render(request, 'survey.html', context=context)
    
    elif request.method == 'POST':
        
        # Check whether all the required fields are filled out
        required_fields = ['student_name', 'school_email', 'q1', 'q2', 'q3', 'q4', 'q5']
        missing_fields = [field for field in required_fields if field not in request.data]

        if missing_fields:
            return JsonResponse({"success": False, "error": f"Missing fields: {', '.join(missing_fields)}"})

        # Important: You can't return a @api_view within another @api_view
        return _handle_student_responses(request)


def _handle_student_responses(request):
    """
    A function that serializes student responses, returns proper Json responses and saves them to the database.
    """
    # Get the email and validate it ends with .edu
    school_email = request.data.get('school_email')
    
    # Check if email ends with .edu
    if not school_email.endswith('.edu'):
        return JsonResponse({
            "success": False,
            "message": "Please use a valid .edu email address.",
            "error": "Invalid email domain. Only .edu email addresses are accepted."
        })
        
    # Check if the student should be flagged
    flagged = False
    if any(getattr(request.data, f'q{i}') >= 3 for i in range(1, 6)):
        flagged = True

    # Save the student response
    student = User.objects.filter(email=request.COOKIES.get("user_email")).first()
    survey_response_serializer_data = {
        "student": student,
        "q1": request.data["q1"],
        "q2": request.data["q2"],
        "q3": request.data["q3"],
        "q4": request.data["q4"],
        "q5": request.data["q5"],
        "flagged": flagged,
    }

    survey_response_serializer = SurveyResponseSerializer(data=survey_response_serializer_data)
    if survey_response_serializer.is_valid():
        
        # Save the response to the database
        survey_response_serializer.save()

        # Return success response
        response_data = {
            "success": True,
            "message": "Thank you for your honest response! Your input makes a difference.",
            "data": survey_response_serializer.data,
        }
        return JsonResponse(response_data)
    
    else:

        # Return error response if serializer errors
        logger.error("Serializer Errors: %s", survey_response_serializer.errors)
        return JsonResponse({
            "success": False,
            "message": "There was an error with your submission.",
            "data": survey_response_serializer.errors
        })


@api_view(['GET'])
def student_response_view(request):
    """
    student_response_view is an API view that returns all survey responses
    saved in the database
    """
    if request.method == "GET":
        survey_responses = SurveyResponse.objects.all()
        survey_response_serializer = SurveyResponseSerializer(survey_responses, many=True)
        return Response(survey_response_serializer.data)
    
    else:
        return HttpResponseBadRequest("Request method not allowed")
    

@api_view(["GET"])
def students_view(request):
    """
    students_view is an API view that returns all students
    in the database
    """
    if request.method == "GET":
        all_students = Student.objects.all()
        students_serializer = StudentSerializer(all_students, many=True)
        return Response(students_serializer.data)
    
    else:
        return HttpResponseBadRequest("Request method not allowed")
    

def dashboard_view(request, university_id):
    """
    dashboard_view returns the dashboard page for a particular university

    university_id: id corresponding to the university
    """
    # Number of students registered in the unviersity
    num_students = len(Student.objects.filter(university_id = university_id))

    # List of students registered in the university and marked as flagged
    all_flagged_students = FlaggedStudent.objects.all()
    school_flagged_students = []
    for student in all_flagged_students:
        if student.student_response.university_id == university_id:
            school_flagged_students.append((student.student_name, student.school_email))

    # Number of students registered in the university and marked as flagged
    num_flagged_students = len(school_flagged_students)

    # Number of responses for students registered in the university
    all_responses = SurveyResponse.objects.filter(university_id = university_id)
    num_responses = len(all_responses)

    num_good_sleep_quality = len([response for response in all_responses if response.q4 <= 2]) # Number of students with good sleep quality
    num_bad_sleep_quality = len([response for response in all_responses if response.q4 >= 4])  # Number of students with bad sleep quality
    num_low_stress = len([response for response in all_responses if response.q1 <= 2])         # Number of students with low stress
    num_moderate_stress = len([response for response in all_responses if response.q1 == 3])    # Number of students with moderate stress
    num_high_stress = len([response for response in all_responses if response.q1 >= 3])        # Number of students with high stress


    months = list(calendar.month_abbr[1:all_responses.order_by("-created")[0].created.month + 1]) # Months in the current calendar year
    months_idx = range(1, all_responses.order_by("-created")[0].created.month + 1)                # Indexes for months in the current calendar year
    monthly_response_rates = []     # Monthly response rates trend
    monthly_num_responses = []      # Monthly number of responses trend
    monthly_support_perception = [] # Monthly support perception trend
    
    # Compute monthly trends
    for month in months_idx:
        month_responses = all_responses.filter(created__year = timezone.now().year, created__month = month) # All responses in the current month
        month_num_responses = len(month_responses)                                                          # Number of responses in the current month
        monthly_response_rates.append(int(month_num_responses/num_students * 100))                          # Response rate for the current month
        monthly_num_responses.append(month_num_responses)                                                   # Number of responses in the current month
        monthly_support_perception.append(len(month_responses.filter(q5__lte = 2)))                         # Number of people feeling supported in the current month

    context = {
        "num_students": num_students, "flagged_students": school_flagged_students, 
        "num_flagged_students": num_flagged_students, "num_responses": num_responses,
        "response_rate": int(num_responses/num_students * 100) if num_students > 0 else 0,
        "num_stable_students": num_responses - num_flagged_students, "num_good_sleep_quality": num_good_sleep_quality,
        "num_bad_sleep_quality": num_bad_sleep_quality, "num_low_stress": num_low_stress,
        "num_moderate_stress": num_moderate_stress, "num_high_stress": num_high_stress,
        "months": months, "monthly_response_rates": monthly_response_rates, "monthly_num_responses": monthly_num_responses,
        "monthly_support_perception": monthly_support_perception
    }

    return render(request, 'dashboard.html', context=context)


def login_view(request):
    """
    login_view allows users to login to the system
    """
    if request.method == "POST":

        # Extract form data
        email = request.POST['email']
        password = request.POST['password']
        university_id = email.split('@')[1].split('.')[0] if '@' in email else 'Unknown'

        # Authenticate user
        user = authenticate(request, email=email, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, "Login Successful!")
            
            # Set cookies for frontend authentication
            response = None
            
            # Redirect to university dashboard if admin is registered with the system
            if User.objects.filter(email=email).first().is_institution_admin:
                response = redirect(reverse('dashboard', kwargs={'university_id': university_id}))
            else:
                response = redirect('survey')
            
            # Keep authentication token and email alive for 7 days
            response.set_cookie('auth_token', request.session.session_key, max_age=3600*24*7)
            response.set_cookie('user_email', email, max_age=3600*24*7)
            
            return response
        
        else:
            messages.error(request, "Invalid username or password")
            return render(request, 'login.html')
        
    elif request.method == "GET":
        return render(request, 'login.html')

    else:
        return HttpResponseBadRequest("Request method not allowed")


def register_view(request):
    """
    register_view allows users to register into the system
    """
    if request.method == "POST":

        # Extract form data
        institution_name = request.POST.get("institution_name")
        name=request.POST.get("name")
        email = request.POST.get("email")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        # Check if password and confirm_password match
        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return redirect("register")

        # Check if user already exists
        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
            return redirect("register")
        
        # Check if the email address matches the institution's patter
        institution_details = Institution.objects.filter(institution_name=institution_name).first()
        match_object = re.fullmatch(institution_details.institution_email_regex, email)
        if not match_object:
            messages.error(request, "Email does not match institution's format")
            return redirect("register")
        
        # Create a new student
        institution_details = Institution.objects.filter(institution_name=institution_name)
        student = User.objects.create_student(email=email, password=password, institution_details=institution_details.first(), name=name)
        student.save()
        messages.success(request, "Registration successful! Please log in.")
        return redirect("login")
    
    elif request.method == "GET":

        # Get all institutions
        institutions = Institution.objects.all()
        institution_names = [institution.institution_name for institution in institutions]
        context = {
            "institution_names": institution_names
        }
        return render(request, "register.html", context=context)

    else:
        return HttpResponseBadRequest("Request method not allowed")


def logout_view(request):
    """
    logout_view allows users to logout of the system
    """
    logout(request)

    # Clear auth cookies
    response = redirect('index')
    response.delete_cookie('auth_token')
    response.delete_cookie('user_email')
    
    messages.success(request, "You have been logged out successfully.")
    
    return response