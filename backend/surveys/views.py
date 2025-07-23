import logging
import calendar
import re
from .models import SurveyResponse, User, Institution, AnonymousStudent, SurveyTemplate, SurveyQuestion, QuestionResponse, QuestionType, QuestionCategory
from .serializers import SurveyResponseSerializer, UserSerializer, InstitutionSerializer, SurveyTemplateSerializer, SurveyQuestionSerializer, AnonymousStudentSerializer
from django.shortcuts import render, redirect
from django.utils import timezone
from django.http import JsonResponse, HttpResponseBadRequest, QueryDict
from django.contrib.auth import authenticate, login, logout
from django.urls import reverse
from django.contrib import messages
from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
import json
from django.db.models import Q
from django.conf import settings
from django.core.cache import cache
from datetime import datetime
from surveys.tasks import analyze_survey_responses_async


# Use a single logger configuration
logger = logging.getLogger("surveys")

@ensure_csrf_cookie
def set_csrf_token(request):
    return JsonResponse({'detail': 'CSRF cookie set'})

def demo_survey_view(request):
    """
    demo_survey_view renders a sample survey response to visitors
    """
    if request.method == "GET":
        return render(request, "demo_survey.html")

@api_view(["GET"])
def user_view(request):
    """user_view returns the current user status"""
    if request.user.is_authenticated:
        # Create the response first
        response = Response(UserSerializer(request.user).data)
        
        # Check and set missing cookies
        if not request.COOKIES.get('auth_token'):
            response.set_cookie(
                'auth_token', 
                request.session.session_key, 
                max_age=3600*24*7, 
                path='/', 
                domain=settings.COOKIE_DOMAIN,
                secure=settings.COOKIE_SECURE,
                httponly=False,
                samesite='Lax'
            )
        
        if not request.COOKIES.get('user_email'):
            response.set_cookie(
                'user_email', 
                request.user.email, 
                max_age=3600*24*7, 
                path='/', 
                domain=settings.COOKIE_DOMAIN,
                secure=settings.COOKIE_SECURE,
                httponly=False,
                samesite='Lax'
            )
            
        if not request.COOKIES.get('is_superuser'):
            response.set_cookie(
                'is_superuser', 
                'true' if request.user.is_superuser else 'false', 
                max_age=3600*24*7, 
                path='/', 
                domain=settings.COOKIE_DOMAIN,
                secure=settings.COOKIE_SECURE,
                httponly=False,
                samesite='Lax'
            )
            
        if not request.COOKIES.get('is_institution_admin'):
            response.set_cookie(
                'is_institution_admin', 
                'true' if request.user.is_institution_admin else 'false', 
                max_age=3600*24*7, 
                path='/', 
                domain=settings.COOKIE_DOMAIN,
                secure=settings.COOKIE_SECURE,
                httponly=False,
                samesite='Lax'
            )
        
        return response
    else:
        return Response({"error": "User not authenticated"}, status=401)

@api_view(["POST"])
def survey_view(request, hash_link=None):
    """survey_view allows students to access the survey page and save survey responses"""
    # Handle hash link survey submission
    if hash_link:
        try:
            survey_template = SurveyTemplate.objects.get(hash_link=hash_link)
            # Get all questions for this template
            questions = SurveyQuestion.objects.filter(survey_template=survey_template)
            if not questions.exists():
                return JsonResponse({"success": False, "message": "No questions found in the survey template"})
            
            # Check if all questions have responses
            missing_responses = []
            for question in questions:
                question_id = str(question.id)
                if question_id not in request.data:
                    missing_responses.append(question.question_text[:30] + "...")
            
            if missing_responses:
                return JsonResponse({"success": False, "message": f"Missing responses for questions: {', '.join(missing_responses)}"})

            # Handle the survey submission
            return _handle_student_responses(request, survey_template, questions, True)
            
        except SurveyTemplate.DoesNotExist:
            return JsonResponse({"success": False, "message": "Survey template not found"}, status=404)
    # Check if a valid user is submitting the response
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "message": "Please login to the application to submit a survey response"})
    # Get the survey template - either from request or use a default
    survey_template_id = request.data.get('survey_template_id')
    if not survey_template_id:
        # Try to get the used template first
        if request.user.institution_details:
            try:
                survey_template = SurveyTemplate.objects.filter(
                    institution=request.user.institution_details,
                    used=True
                ).first()
                
                # If no used template exists, fall back to the one with minimal ID
                if not survey_template:
                    survey_template = SurveyTemplate.objects.filter(
                        institution=request.user.institution_details
                    ).order_by('id').first()
                    
                    # If we found a template, mark it as used
                    if survey_template:
                        survey_template.used = True
                        survey_template.save()
                
                if not survey_template:
                    return JsonResponse({"success": False, "message": "No survey template found for your institution"})
            except Exception as e:
                return JsonResponse({"success": False, "message": f"Error finding survey template: {str(e)}"})
        else:
            return JsonResponse({"success": False, "message": "No institution associated with user and no survey template specified"})
    else:
        try:
            survey_template = SurveyTemplate.objects.get(id=survey_template_id)
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Invalid survey template: {str(e)}"})

    # Get all questions for this template
    questions = SurveyQuestion.objects.filter(survey_template=survey_template)
    if not questions.exists():
        return JsonResponse({"success": False, "message": "No questions found in the survey template"})
    
    # Check if all questions have responses
    missing_responses = []
    for question in questions:
        question_id = str(question.id)
        if question_id not in request.data:
            missing_responses.append(question.question_text[:30] + "...")
    
    if missing_responses:
        return JsonResponse({"success": False, "message": f"Missing responses for questions: {', '.join(missing_responses)}"})

    # Important: You can't return a @api_view within another @api_view
    return _handle_student_responses(request, survey_template, questions, False)


def _handle_student_responses(request, survey_template, questions, hashed=False):
    """
    A function that serializes student responses, returns proper Json responses and saves them to the database.
    """
    no_student_user = False
    if hashed:
        student_name = request.data.get('student_name')
        school_email = request.data.get('school_email')
        institution_email_regex = survey_template.institution.institution_regex_pattern
        if not re.fullmatch(institution_email_regex, school_email, re.IGNORECASE):
            return JsonResponse({
                "success": False,
                "message": "Please use your institution email. Normally should end with .edu"
            })
        student = User.objects.filter(is_student=True, email=school_email).first()
        if not student:
            no_student_user=True
            ano_student, created = AnonymousStudent.objects.get_or_create(
                email=school_email,
                defaults={'name': student_name, 'survey_template': survey_template}
            )
        else:
            # Registered user exists with this email
            if not request.user.is_authenticated:
                # They need to log in first
                return JsonResponse({
                    "success": False,
                    "requires_auth": True,
                    "message": "This email is already registered. Please log in to submit your survey.",
                })
            else:
                # They're already logged in - use their account
                student = request.user
                no_student_user = False
            
    else:
        # Get the email and validate it ends with .edu
        school_email = request.user.email

        # Save the student response
        student = request.user
    
        # Update student name if provided
        if 'student_name' in request.data and not student.name:
            student.name = request.data['student_name']
            student.save()
    
    # Create the survey response
    try:
        if not no_student_user:
            survey_response = SurveyResponse.objects.create(
                student=student,
                survey_template=survey_template,
                flagged=False  # Will update this after checking responses
            )
        else:
            survey_response = SurveyResponse.objects.create(
                anonymous_student=ano_student,
                survey_template = survey_template,
                flagged=False
            )
        
        # Create individual question responses
        should_flag = False
        for question in questions:
            question_id = str(question.id)
            response_value = request.data.get(question_id)
            
            if question.question_type == 'likert':
                likert_value = int(response_value)
                text_response = None
                # Check if this response should trigger flagging
                if likert_value >= 3:  # Assuming 3+ is concerning for any question
                    should_flag = True
            else:  # text response
                likert_value = None
                text_response = response_value
            
            QuestionResponse.objects.create(
                survey_response=survey_response,
                question=question,
                likert_value=likert_value,
                text_response=text_response
            )
        
        # Update flagged status if needed
        if should_flag:
            survey_response.flagged = True
            survey_response.save()
        
        # Pass question IDs instead of model objects
        question_ids = [q.id for q in questions]
        result = analyze_survey_responses_async.delay(survey_response.id, question_ids)

        # Return success response
        response_data = {
            "success": True,
            "message": "Thank you for your honest response! Your input makes a difference.",
            "redirect_url": "/",
            "data": SurveyResponseSerializer(survey_response).data,
        }
        return JsonResponse(response_data)
    
    except Exception as e:
        # Return error response if any errors occur
        logger.error("Error saving survey response: %s", str(e))
        return JsonResponse({
            "success": False,
            "message": "There was an error with your submission.",
        })

@api_view(["GET"])
def get_user_survey_questions(request, hash_link=None):
    """
    API endpoint to get survey questions for the current user based on their institution
    """
    # Handle hash link requests (authentication required)
    if hash_link:
        try:
            survey_template = SurveyTemplate.objects.get(hash_link=hash_link)
            
            # Get all questions for this template
            questions = SurveyQuestion.objects.filter(survey_template=survey_template).order_by('order')
            
            if not questions.exists():
                return JsonResponse({
                    "success": False, 
                    "error": "No survey questions found for this template"
                }, status=404)
            
            # Serialize the questions
            questions_data = [{
                'id': q.id,
                'text': q.question_text,
                'type': q.question_type,
                'category': q.category,
                'answer_choices': q.answer_choices,
                'order': q.order
            } for q in questions]
            
            return JsonResponse({
                "success": True, 
                "template_id": survey_template.id,
                "questions": questions_data
            })
            
        except SurveyTemplate.DoesNotExist:
            return JsonResponse({
                "success": False, 
                "error": "Survey template not found"
            }, status=404)

    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required"})
    try:
        survey_template = None
        
        # If user is a student, get template by institution
        if not request.user.is_superuser:
            if request.user.institution_details:
                survey_template = SurveyTemplate.objects.filter(
                    institution=request.user.institution_details,
                    used=True
                ).first()
                
            if not survey_template:
                survey_template = SurveyTemplate.objects.filter(
                    institution=request.user.institution_details,
                ).order_by('id').first()
        
        # If user is a superuser, get any template (for testing)
        elif request.user.is_superuser:
            survey_template = SurveyTemplate.objects.first()
        
        if not survey_template:
            return JsonResponse({
                "success": False, 
                "error": "No survey template found for your institution"
            }, status=404)
        
        # Get all questions for this template
        questions = SurveyQuestion.objects.filter(survey_template=survey_template).order_by('order')
        
        # Check if questions exist
        if not questions.exists():
            return JsonResponse({
                "success": False, 
                "error": "No survey questions found for this template"
            }, status=404)
        
        # Serialize the questions
        questions_data = [{
            'id': q.id,
            'text': q.question_text,
            'type': q.question_type,
            'category': q.category,
            'answer_choices': q.answer_choices,
            'order': q.order
        } for q in questions]
        
        # Final check - make sure we have questions data
        if not questions_data:
            return JsonResponse({
                "success": False, 
                "error": "Survey questions could not be loaded"
            }, status=500)
        
        return JsonResponse({
            "success": True, 
            "template_id": survey_template.id,
            "questions": questions_data
        })
        
    except Exception as e:
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching survey questions: {str(e)}")
        
        return JsonResponse({
            "success": False, 
            "error": "An error occurred while loading survey questions"
        }, status=500)

@api_view(["GET"])
def dashboard_api(request):
    """
    dashboard_view returns the dashboard page for a particular university.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    
    if request.user.is_superuser:
        return JsonResponse({"error": "Superuser access not allowed"}, status=403)
    
    if not request.user.is_institution_admin:
        return JsonResponse({"error": "Admin access required"}, status=403)
    
    # Get the institution details of the admin
    institution_details = request.user.institution_details

    # Number of students registered in the university
    num_registered_students = len(User.objects.filter(is_student=True, institution_details=institution_details))

    num_anonymous_students = len(AnonymousStudent.objects.filter(survey_template__institution=institution_details))

    num_students = num_registered_students+num_anonymous_students

    responded_students = 0
    # Get all students in the institution
    institution_students = User.objects.filter(is_student=True, institution_details=institution_details)
    
    anonymous_students = AnonymousStudent.objects.filter(survey_template__institution=institution_details)

    # Initialize list for flagged students
    school_flagged_responses = []
    
    # For each student, check if their latest response is flagged
    for student in institution_students:
        # Get the latest response for this student
        latest_response = SurveyResponse.objects.filter(student=student).order_by('-created').first()
        if latest_response:
            responded_students += 1
        # If the student has a response and it's flagged, add them to the list
        if latest_response and latest_response.flagged:
            school_flagged_responses.append((student.name, student.email))

    # For each anonymous student, check if their latest response is flagged
    for anon_student in anonymous_students:
        # Get the latest response for this student
        latest_response = SurveyResponse.objects.filter(anonymous_student=anon_student).order_by('-created').first()
        if latest_response:
            responded_students += 1
        # If the student has a response and it's flagged, add them to the list
        if latest_response and latest_response.flagged:
            school_flagged_responses.append((anon_student.name or "Anonymous", anon_student.email))

    # Number of responses for students registered in the university
    all_registered_responses = SurveyResponse.objects.filter(student__institution_details=institution_details)
    all_anonymous_responses = SurveyResponse.objects.filter(anonymous_student__survey_template__institution=institution_details)
    num_responses = len(all_registered_responses)+len(all_anonymous_responses)
    all_responses = SurveyResponse.objects.filter(
    Q(student__institution_details=institution_details) | 
    Q(anonymous_student__survey_template__institution=institution_details)
)
    
    # Number of students registered in the university and marked as flagged
    num_flagged_students = len(school_flagged_responses)
    
    # Get all survey templates for this institution
    survey_templates = SurveyTemplate.objects.filter(institution=institution_details)
    
    # Check if there are sleep quality questions
    has_sleep_questions = SurveyQuestion.objects.filter(
        survey_template__in=survey_templates,
        category=QuestionCategory.SLEEP
    ).exists()
    
    # Check if there are stress level questions
    has_stress_questions = SurveyQuestion.objects.filter(
        survey_template__in=survey_templates,
        category=QuestionCategory.STRESS
    ).exists()
    
    # Check if there are support perception questions
    has_support_questions = SurveyQuestion.objects.filter(
        survey_template__in=survey_templates,
        category=QuestionCategory.SUPPORT
    ).exists()
    
    # Initialize metrics with default values
    num_good_sleep_quality = 0
    num_bad_sleep_quality = 0
    num_low_stress = 0
    num_moderate_stress = 0
    num_high_stress = 0
    monthly_support_perception = []
    
    # Only calculate sleep metrics if sleep questions exist
    if has_sleep_questions:
        # Find sleep quality questions
        sleep_questions = SurveyQuestion.objects.filter(
            survey_template__in=survey_templates,
            category=QuestionCategory.SLEEP
        )
        
        # Get responses for sleep questions
        for response in all_responses:
            for sleep_question in sleep_questions:
                try:
                    question_response = QuestionResponse.objects.get(
                        survey_response=response,
                        question=sleep_question
                    )
                    if question_response.likert_value is not None:
                        if question_response.likert_value <= 2:
                            num_good_sleep_quality += 1
                        elif question_response.likert_value >= 4:
                            num_bad_sleep_quality += 1
                except QuestionResponse.DoesNotExist:
                    continue
    
    # Only calculate stress metrics if stress questions exist
    if has_stress_questions:
        # Find stress level questions
        stress_questions = SurveyQuestion.objects.filter(
            survey_template__in=survey_templates,
            category=QuestionCategory.STRESS
        )
        
        # Get responses for stress questions
        for response in all_responses:
            for stress_question in stress_questions:
                try:
                    question_response = QuestionResponse.objects.get(
                        survey_response=response,
                        question=stress_question
                    )
                    if question_response.likert_value is not None:
                        if question_response.likert_value <= 2:
                            num_low_stress += 1
                        elif question_response.likert_value == 3:
                            num_moderate_stress += 1
                        elif question_response.likert_value >= 4:
                            num_high_stress += 1
                except QuestionResponse.DoesNotExist:
                    continue

    months = []
    months_idx = []
    monthly_response_rates = []
    monthly_num_responses = []
    
    # Only process if there are responses
    if all_responses.exists():
        months = list(calendar.month_abbr[1:all_responses.order_by("-created")[0].created.month + 1])
        months_idx = range(1, all_responses.order_by("-created")[0].created.month + 1)
        
        # Compute monthly trends
        for month in months_idx:
            # Get all responses for this month
            month_responses = all_responses.filter(created__year=timezone.now().year, created__month=month)
            
            # Count unique students who responded in this month
            registered_responded = month_responses.filter(student__isnull=False).values('student').distinct().count()
            anonymous_responded = month_responses.filter(anonymous_student__isnull=False).values('anonymous_student').distinct().count()  
            unique_students_responded = registered_responded + anonymous_responded
            # Calculate response rate based on unique students
            monthly_response_rates.append(int(unique_students_responded/num_students * 100) if num_students > 0 else 0)
            
            # Store the count of unique student responses
            monthly_num_responses.append(unique_students_responded)
            
            # Only calculate support perception if support questions exist
            if has_support_questions:
                # Rest of the support perception calculation remains the same
                support_count = 0
                support_questions = SurveyQuestion.objects.filter(
                    survey_template__in=survey_templates,
                    category=QuestionCategory.SUPPORT
                )
                
                for response in month_responses:
                    for support_question in support_questions:
                        try:
                            question_response = QuestionResponse.objects.get(
                                survey_response=response,
                                question=support_question
                            )
                            if question_response.likert_value is not None and question_response.likert_value <= 2:
                                support_count += 1
                        except QuestionResponse.DoesNotExist:
                            continue
                
                monthly_support_perception.append(support_count)

    context = {
        "num_students": num_students, 
        "flagged_students": school_flagged_responses, 
        "num_flagged_students": num_flagged_students, 
        "num_responses": num_responses,
        "response_rate": int(responded_students/num_students * 100) if num_students > 0 else 0,
        "num_stable_students": num_students - num_flagged_students, 
        "num_good_sleep_quality": num_good_sleep_quality,
        "num_bad_sleep_quality": num_bad_sleep_quality, 
        "num_low_stress": num_low_stress,
        "num_moderate_stress": num_moderate_stress, 
        "num_high_stress": num_high_stress,
        "months": months, 
        "monthly_response_rates": monthly_response_rates, 
        "monthly_num_responses": monthly_num_responses,
        "monthly_support_perception": monthly_support_perception,
        "has_sleep_questions": has_sleep_questions,
        "has_stress_questions": has_stress_questions,
        "has_support_questions": has_support_questions
    }

    return JsonResponse(context)

@api_view(["POST"])
def login_view(request):
    if request.method == "POST":
        try:
            # Check if body exists
            if not request.body:
                return JsonResponse({'error': 'No data provided'}, status=400)
            
            # Parse JSON
            data = json.loads(request.body)
            email = data.get('email')
            password = data.get('password')
            
            # Check if email/password provided
            if not email or not password:
                return JsonResponse({'error': 'Email and password required'}, status=400)
            
            user = authenticate(request, email=email, password=password)
            
            if user is not None:
                login(request, user)
                
                response = JsonResponse({
                    'success': True,
                    'message': 'Login successful!',
                    'is_admin': user.is_institution_admin,
                    'redirect_path': '/dashboard/' if user.is_institution_admin else '/survey/'
                })
                
                # Production-ready cookie settings
                response.set_cookie(
                    'auth_token', 
                    request.session.session_key, 
                    max_age=3600*24*7,
                    path='/',
                    domain=settings.COOKIE_DOMAIN,
                    secure=settings.COOKIE_SECURE,
                    httponly=False,
                    samesite='Lax'
                )
                response.set_cookie(
                    'user_email', 
                    email, 
                    max_age=3600*24*7,
                    path='/',
                    domain=settings.COOKIE_DOMAIN,
                    secure=settings.COOKIE_SECURE,
                    httponly=False,
                    samesite='Lax'
                )
                response.set_cookie(
                    'is_superuser', 
                    'true' if user.is_superuser else 'false', 
                    max_age=3600*24*7,
                    path='/',
                    domain=settings.COOKIE_DOMAIN,
                    secure=settings.COOKIE_SECURE,
                    httponly=False,
                    samesite='Lax'
                )
                response.set_cookie(
                    'is_institution_admin', 
                    'true' if user.is_institution_admin else 'false', 
                    max_age=3600*24*7,
                    path='/',
                    domain=settings.COOKIE_DOMAIN,
                    secure=settings.COOKIE_SECURE,
                    httponly=False,
                    samesite='Lax'
                )
                
                return response
            else:
                return JsonResponse({'success': False, 'message': 'Invalid credentials'}, status=400)
                
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON format'}, status=400)
        except Exception as e:
            print(f"Login error: {e}")  # This will show in Django console
            return JsonResponse({'error': 'Server error occurred'}, status=500)
    return JsonResponse({'error': 'Use POST method'}, status=405)

@api_view(["POST"])
def register_view(request):
    """
    register_view allows users to register into the system via API
    """
    if request.method == "POST":
        # Extract form data from request.data (for JSON) or request.POST (for form data)
        data = request.data if request.data else request.POST
        
        institution_name = data.get("institution_name")
        name = data.get("name")
        email = data.get("email")
        password = data.get("password")
        confirm_password = data.get("confirm_password")

        # Validation checks
        if password != confirm_password:
            return Response({
                'success': False,
                'message': "Passwords do not match."
            }, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=email).exists():
            return Response({
                'success': False,
                'message': "Email already registered."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if the institution exists
        institution_details = Institution.objects.filter(institution_name=institution_name)
        if not institution_details.exists():
            return Response({
                'success': False,
                'message': "Institution does not exist"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if the email address matches the institution's pattern
        institution_details = institution_details.first()
        match_object = re.fullmatch(institution_details.institution_regex_pattern, email, re.IGNORECASE)
        if not match_object:
            return Response({
                'success': False,
                'message': "Email does not match institution's format"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create a new student
        try:
            student = User.objects.create_student(
                email=email, 
                password=password, 
                institution_details=institution_details, 
                name=name
            )
            student.save()
            
            return Response({
                'success': True,
                'message': "Registration successful! Please log in."
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({
                'success': False,
                'message': "Registration failed. Please try again."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["POST"])
def logout_view(request):
    """
    logout_view allows users to logout of the system
    """
    logout(request)

    # Create response with success message
    response_data = {
        "success": True,
        "message": "You have been logged out successfully."
    }
    
    response = JsonResponse(response_data)
    
    # Clear auth cookies
    cookies_to_clear = [
        'sessionid',
        'auth_token', 
        'user_email', 
        'is_institution_admin', 
        'is_superuser'
    ]
    
    for cookie_name in cookies_to_clear:
        response.delete_cookie(
            cookie_name, 
            path="/", 
            domain=settings.COOKIE_DOMAIN,
        )
    
    return response


# NOTE: API views are WIP. Need to add parameters for filtering db records
@api_view(['GET'])
def student_response_view(request):
    """
    student_response_view is an API view that returns survey responses
    - Superusers see all responses
    - Institution admins see only responses from their institution
    """
    if request.method == "GET" and request.user.is_authenticated and (request.user.is_superuser or request.user.is_institution_admin):
        if request.user.is_superuser:
            # Superuser sees all responses
            survey_responses = SurveyResponse.objects.all()
        else:
            # Institution admin sees only responses from their institution
            # This includes both registered students and anonymous students from their institution
            survey_responses = SurveyResponse.objects.filter(
                Q(student__institution_details=request.user.institution_details) |
                Q(anonymous_student__survey_template__institution=request.user.institution_details)
            )
        
        survey_response_serializer = SurveyResponseSerializer(survey_responses, many=True)
        return Response(survey_response_serializer.data)
    
    else:
        return HttpResponseBadRequest("Request method not allowed")


@api_view(["GET"])
def flagged_responses_view(request):
    """
    flagged_responses_view is an API view that returns flagged survey responses
    - Superusers see all flagged responses
    - Institution admins see only flagged responses from their institution
    """
    if request.method == "GET" and request.user.is_authenticated and (request.user.is_superuser or request.user.is_institution_admin):
        if request.user.is_superuser:
            # Superuser sees all flagged responses
            flagged_students = SurveyResponse.objects.filter(flagged=True)
        else:
            # Institution admin sees only flagged responses from their institution
            flagged_students = SurveyResponse.objects.filter(
                flagged=True
            ).filter(
                Q(student__institution_details=request.user.institution_details) |
                Q(anonymous_student__survey_template__institution=request.user.institution_details)
            )
        
        flagged_students_serializer = SurveyResponseSerializer(flagged_students, many=True)
        return Response(flagged_students_serializer.data)
    
    else:
        return HttpResponseBadRequest("Request method not allowed")
    
@api_view(["GET"])
def students_view(request):
    """
    students_view is an API view that returns students (both registered and anonymous)
    - Superusers see all students
    - Institution admins see only students from their institution
    """
    if request.method == "GET" and request.user.is_authenticated and (request.user.is_superuser or request.user.is_institution_admin):
        if request.user.is_superuser:
            # Superuser sees all students
            all_students = User.objects.filter(is_student=True)
            all_anonymous_students = AnonymousStudent.objects.all()
        else:
            # Institution admin sees only students from their institution
            all_students = User.objects.filter(
                is_student=True,
                institution_details=request.user.institution_details
            )
            all_anonymous_students = AnonymousStudent.objects.filter(
                survey_template__institution=request.user.institution_details
            )
        
        user_serializer = UserSerializer(all_students, many=True)
        anonymous_serializer = AnonymousStudentSerializer(all_anonymous_students, many=True)
        
        # Combine the data with type indicators
        response_data = {
            "registered_students": user_serializer.data,
            "anonymous_students": anonymous_serializer.data
        }
        
        return Response(response_data)
    
    else:
        return HttpResponseBadRequest("Request method not allowed")

@api_view(["GET"])
def flagged_students_view(request):
    """
    flagged_students_view returns all students (registered and anonymous) whose latest survey response is flagged.
    Only returns unique students, not all their responses.
    
    Access: Institution admins see their institution's students, superusers see all.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    
    if not (request.user.is_superuser or request.user.is_institution_admin):
        return JsonResponse({"error": "Admin access required"}, status=403)
    
    try:
        flagged_registered_students = []
        flagged_anonymous_students = []
        
        # Handle registered students
        if request.user.is_superuser:
            students = User.objects.filter(is_student=True)
        else:
            students = User.objects.filter(
                is_student=True, 
                institution_details=request.user.institution_details
            )
        
        # Check each registered student's latest response
        for student in students:
            latest_response = SurveyResponse.objects.filter(
                student=student
            ).order_by('-created').first()
            
            # If latest response exists and is flagged, include this student
            if latest_response and latest_response.flagged:
                flagged_registered_students.append({
                    "id": student.id,
                    "name": student.name,
                    "email": student.email,
                    "institution_id": student.institution_details.id if student.institution_details else None,
                    "institution_name": student.institution_details.institution_name if student.institution_details else None,
                    "latest_response_date": latest_response.created,
                    "latest_response_id": latest_response.id
                })
        
        # Handle anonymous students
        if request.user.is_superuser:
            anonymous_students = AnonymousStudent.objects.all()
        else:
            anonymous_students = AnonymousStudent.objects.filter(
                survey_template__institution=request.user.institution_details
            )
        
        # Check each anonymous student's latest response
        for anonymous_student in anonymous_students:
            latest_response = SurveyResponse.objects.filter(
                anonymous_student=anonymous_student
            ).order_by('-created').first()
            
            # If latest response exists and is flagged, include this anonymous student
            if latest_response and latest_response.flagged:
                flagged_anonymous_students.append({
                    "email": anonymous_student.email,
                    "name": anonymous_student.name,
                    "institution_id": anonymous_student.survey_template.institution.id if anonymous_student.survey_template else None,
                    "institution_name": anonymous_student.survey_template.institution.institution_name if anonymous_student.survey_template else None,
                    "survey_template_id": anonymous_student.survey_template.id if anonymous_student.survey_template else None,
                    "latest_response_date": latest_response.created,
                    "latest_response_id": latest_response.id,
                    "created_at": anonymous_student.created_at
                })
        
        return JsonResponse({
            "success": True,
            "registered_students": {
                "count": len(flagged_registered_students),
                "students": flagged_registered_students
            },
            "anonymous_students": {
                "count": len(flagged_anonymous_students),
                "students": flagged_anonymous_students
            },
            "total_count": len(flagged_registered_students) + len(flagged_anonymous_students)
        })
        
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": f"Error retrieving flagged students: {str(e)}"
        }, status=500)

@api_view(["GET"])
def institutions_view(request):
    """
    institution_view is an API view that returns all students
    in the database
    """
    if request.method == "GET":
        all_institutions = Institution.objects.all()
        institution_serializer = InstitutionSerializer(all_institutions, many=True)
        return Response(institution_serializer.data)
    
    else:
        return HttpResponseBadRequest("Request method not allowed")

@api_view(["GET"])
def survey_templates_admin_view(request):
    if request.method == "GET" and request.user.is_authenticated and request.user.is_institution_admin:
        return render(request, "survey_templates_admin.html")
    
    else:
        return HttpResponseBadRequest("Request method not allowed")

@api_view(["GET", "POST", "DELETE"])
def survey_templates_view(request):
    """
    API to list, create and delete survey templates
    """
    if not request.user.is_authenticated or not request.user.is_institution_admin:
        return JsonResponse({"success": False, "error": "Permission denied"})
    
    if request.method == "GET":
        # List all survey templates for the admin's institution
        templates = SurveyTemplate.objects.filter(institution=request.user.institution_details)
        serializer = SurveyTemplateSerializer(templates, many=True)
        return JsonResponse({"success": True, "templates": serializer.data})
    
    elif request.method == "POST":
        # Create a new survey template
        try:
            new_template = SurveyTemplate.objects.create(
                institution=request.user.institution_details
            )
            return JsonResponse({
                "success": True,
                "message": "Survey template created",
                "id": new_template.id,
                "hash_link": new_template.hash_link
            })
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})
    
    elif request.method == "DELETE":
        # Delete a survey template
        try:
            data = request.data
            template_id = data.get('template_id')
            
            if not template_id:
                return JsonResponse({"success": False, "error": "Template ID is required"})
            
            template = get_object_or_404(SurveyTemplate, id=template_id)
            
            # Check if the template belongs to the admin's institution
            if template.institution != request.user.institution_details:
                return JsonResponse({"success": False, "error": "You can only delete your institution's templates"})
            
            # Delete the template (this will cascade delete all associated questions)
            template.delete()
            
            return JsonResponse({
                "success": True,
                "message": "Template deleted"
            })
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

@api_view(["GET", "POST", "DELETE"])
def survey_questions_view(request, template_id):
    """
    API to manage questions for a specific survey template
    """
    if not request.user.is_authenticated or not request.user.is_institution_admin:
        return JsonResponse({"success": False, "error": "Permission denied"})
    
    # Get the survey template
    template = get_object_or_404(SurveyTemplate, id=template_id)
    
    # Check if the template belongs to the admin's institution
    if template.institution != request.user.institution_details:
        return JsonResponse({"success": False, "error": "You can only manage your institution's surveys"})
    
    if request.method == "GET":
        # List all questions for this template
        questions = SurveyQuestion.objects.filter(survey_template=template).order_by('order')
        serializer = SurveyQuestionSerializer(questions, many=True)
        return JsonResponse({"success": True, "questions": serializer.data})
    
    elif request.method == "POST":
        # Add a new question to the template
        try:
            data = request.data
            
            # Get the highest current order value
            highest_order = SurveyQuestion.objects.filter(survey_template=template).order_by('-order').first()
            new_order = 1 if not highest_order else highest_order.order + 1
            
            # Create question with basic fields
            new_question = SurveyQuestion(
                survey_template=template,
                question_text=data.get('question_text', 'New Question'),
                question_type=data.get('question_type', QuestionType.LIKERT),
                category=data.get('question_category', QuestionCategory.GENERAL),
                order=new_order,
                answer_choices=data.get('answer_choices')
            )
            
            # Add answer choices if provided
            if data.get('answer_choices') and data.get('question_type') == QuestionType.LIKERT:
                new_question.answer_choices = data.get('answer_choices')
            
            new_question.save()
            
            serializer = SurveyQuestionSerializer(new_question)
            return JsonResponse({
                "success": True,
                "message": "Question added",
                "question": serializer.data
            })
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})
    
    elif request.method == "DELETE":
        # Delete a question from the template
        try:
            data = request.data
            question_id = data.get('question_id')
            
            if not question_id:
                return JsonResponse({"success": False, "error": "Question ID is required"})
            
            question = get_object_or_404(SurveyQuestion, id=question_id, survey_template=template)
            question.delete()
            
            # Reorder remaining questions
            remaining_questions = SurveyQuestion.objects.filter(survey_template=template).order_by('order')
            for i, q in enumerate(remaining_questions, 1):
                q.order = i
                q.save()
            
            return JsonResponse({
                "success": True,
                "message": "Question deleted"
            })
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})


@api_view(["POST"])
def use_template(request, template_id):
    """Activate a specific template for use"""
    if not request.user.is_authenticated or not request.user.is_institution_admin:
        return JsonResponse({"success": False, "error": "Unauthorized"})

    try:
        # Get the template to activate
        template = get_object_or_404(SurveyTemplate, id=template_id, institution=request.user.institution_details)
        
        # Deactivate all other templates for this institution
        SurveyTemplate.objects.filter(institution=request.user.institution_details).update(used=False)
        
        # Activate the selected template
        template.used = True
        template.save()
        
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})

# Modify the existing survey_view to use the 'used' field
def get_active_template(institution):
    """Helper function to get the active template or fallback to the one with minimal ID"""
    # Try to get the used template first
    template = SurveyTemplate.objects.filter(institution=institution, used=True).first()
    
    # If no template is marked as used, get the one with minimal ID
    if not template:
        template = SurveyTemplate.objects.filter(institution=institution).order_by('id').first()
        if template:
            # Automatically mark this template as used
            template.used = True
            template.save()
    
    return template

@api_view(["POST"])
def survey_autosave(request):
    try:
        if not request.user.is_authenticated:
            return JsonResponse({"success": False, "message": "User not authorized"}, status=200)
        data = request.data
        template_id = request.data.get("template_id")  
        if not template_id:
            return JsonResponse({"success": False, "message": "Error: Wrong template id"}, status=200) 
        try: 
            SurveyTemplate.objects.get(id=template_id)
        except SurveyTemplate.DoesNotExist:
            return JsonResponse({
                "success": False, 
                "message": "Invalid survey template"
            }, status=404)     
        answers = request.data.get("answers", {})
        student_name, school_email = request.user.name, request.user.email
        cache_data = {
            "template_id": template_id, 
            "student_name": student_name if student_name else "", 
            "school_email": school_email, 
            "last_saved": datetime.now().isoformat(),
            "answers": answers, 
        }
        cache.set(f"survey_autosave_{school_email}_{template_id}", json.dumps(cache_data), timeout=1800)
        return JsonResponse({"success": True, "message": "Progress saved"})
    except Exception as e:
        logger.error(f"Autosave error: {str(e)}")
        return JsonResponse({"success": False, "message": "Failed to save progress"}, status=200)


@api_view(["GET"])
def survey_autosave_load(request, template_id):
    try:
        # Check authentication
        if not request.user.is_authenticated:
            return JsonResponse({"success": False, "message": "User not authorized"}, status=200)
        school_email = request.user.email
        cache_key = f"survey_autosave_{school_email}_{template_id}"
        cached_data = cache.get(cache_key)
        if cached_data:
            try:
                return JsonResponse({"success": True, "saved_data": json.loads(cached_data)}, status=200)
            except json.JSONDecodeError:
                # Corrupted data
                cache.delete(cache_key)
                return JsonResponse({"success": False, "message": "Corrupted save data. Please press the clear button"}, status=200)
        else:
            return JsonResponse({"success": False, "message": "No autosaved data found"}, status=200)
    except Exception as e:
        logger.error(f"Autosave load error: {str(e)}")
        return JsonResponse({"success": False, "message": "Failed to load autosave"}, status=200)

@api_view(["DELETE"])
def survey_autosave_clear(request, template_id):
    try:
        if not request.user.is_authenticated:
            return JsonResponse({"success": False, "message": "User not authorized"}, status=200)
        school_email = request.user.email
        cache_key = f"survey_autosave_{school_email}_{template_id}"
        
        cache.delete(cache_key)

        return JsonResponse({"success": True, "message": "Autosave data cleared"})
    except Exception as e:
        logger.error(f"Clear autosave error: {str(e)}")
        return JsonResponse({"success": False, "message": "Failed to clear draft"}, status=200)
