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
from django.db.models import Subquery, OuterRef, Count, Q
from django.conf import settings
from django.core.cache import cache
from datetime import datetime
from surveys.tasks import analyze_survey_responses_async
from django.db import transaction, IntegrityError


# Use a single logger configuration
logger = logging.getLogger("surveys")

@ensure_csrf_cookie
def set_csrf_token(request):
    """
    Set CSRF token for the client.
    
    @params:
        request (HttpRequest): The HTTP request object
    
    @returns:
        JsonResponse: JSON response containing CSRF token
        - success (bool): Always True
        - csrfToken (str): The CSRF token for the client
    """
    return JsonResponse({'detail': 'CSRF cookie set'})

def demo_survey_view(request):
    """
    Render the demo survey page.
    
    @params:
        request (HttpRequest): The HTTP request object
    
    @returns:
        HttpResponse: Rendered demo survey HTML template
    """
    if request.method == "GET":
        return render(request, "demo_survey.html")

@api_view(["GET"])
def user_view(request):
    """
    Render the user dashboard page.
    
    @params:
        request (HttpRequest): The HTTP request object
    
    @returns:
        HttpResponse: Rendered user dashboard HTML template
    """
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
                'true' if request.user.role == User.Role.INSTITUTION_ADMIN else 'false', 
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
    """
    Render the survey page for a specific survey template.
    
    @params:
        request (HttpRequest): The HTTP request object
        hash_link (str): Unique hash identifier for the survey template
    
    @returns:
        HttpResponse: Rendered survey HTML template with context data
        Context includes:
        - survey_template: The survey template object
        - questions: List of questions for the survey
        - hash_link: The survey hash link
    """
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
    Handle student survey responses and save them to the database.
    
    @params:
        request (HttpRequest): The HTTP request object containing survey responses
        survey_template (SurveyTemplate): The survey template object
    
    @returns:
        JsonResponse: JSON response indicating success or failure
        - success (bool): True if responses saved successfully, False otherwise
        - message (str): Success or error message
        - response_id (int): ID of the created survey response (on success)
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
        student = User.objects.filter(role=User.Role.STUDENT, email=school_email).first()
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
        with transaction.atomic():
            if not no_student_user:
                recent = SurveyResponse.objects.select_for_update().filter(
                    student=student,
                    survey_template=survey_template,
                    created__gte=timezone.now() - timezone.timedelta(seconds=60)
                ).first()

                if recent:
                    return JsonResponse({
                        "success": False,
                        "message": "You recently submitted this survey. Please wait before submitting again."
                    })

                survey_response = SurveyResponse.objects.create(
                    student=student,
                    survey_template=survey_template,
                    flagged=False  # Will update this after checking responses
                )
            else:
                recent = SurveyResponse.objects.select_for_update().filter(
                    anonymous_student=ano_student,
                    survey_template=survey_template,
                    created__gte=timezone.now() - timezone.timedelta(seconds=60)
                ).first()

                if recent:
                    return JsonResponse({
                        "success": False,
                        "message": "You recently submitted this survey. Please wait before submitting again."
                    })

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
            transaction.on_commit(
                lambda: analyze_survey_responses_async.delay(survey_response.id, question_ids)
            )
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
    @params:
        request (HttpRequest): The HTTP request object
        hash_link (str): Unique hash identifier for the survey template
    
    @returns:
        JsonResponse: JSON response containing survey questions
        - success (bool): True if questions retrieved successfully, False otherwise
        - questions (list): List of question objects with details
        - survey_template (dict): Survey template information
        - error (str): Error message (on failure)
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
    Provides comprehensive dashboard analytics for institution administrators.
    
    This endpoint aggregates and returns statistical data about students, survey responses,
    and mental health metrics for a specific institution. It calculates various metrics
    including response rates, flagged students, sleep quality, stress levels, and monthly trends.
    
    @params:
        request (HttpRequest): Django HTTP request object
            - Must be authenticated
            - User must be an institution admin (not superuser)
            - User must have institution_details associated
    
    @returns:
        JsonResponse: Dashboard analytics data
        
        Success Response (200):
        {
            "num_students": int,                    # Total students (registered + anonymous)
            "flagged_students": list,               # List of tuples [(name, email), ...] for flagged students
            "num_flagged_students": int,            # Count of students with flagged responses
            "num_responses": int,                   # Total number of survey responses
            "response_rate": int,                   # Percentage of students who have responded
            "num_stable_students": int,             # Students without flagged responses
            "num_good_sleep_quality": int,          # Students with good sleep (likert <= 2)
            "num_bad_sleep_quality": int,           # Students with poor sleep (likert >= 4)
            "num_low_stress": int,                  # Students with low stress (likert <= 2)
            "num_moderate_stress": int,             # Students with moderate stress (likert == 3)
            "num_high_stress": int,                 # Students with high stress (likert >= 4)
            "months": list,                         # Month abbreviations for current year up to latest response
            "monthly_response_rates": list,         # Response rate percentages by month
            "monthly_num_responses": list,          # Number of unique student responses by month
            "monthly_support_perception": list,     # Support perception counts by month (if support questions exist)
            "has_sleep_questions": bool,            # Whether institution has sleep category questions
            "has_stress_questions": bool,           # Whether institution has stress category questions
            "has_support_questions": bool           # Whether institution has support category questions
        }
        
        Error Responses:
        - 401: {"error": "Authentication required"} - User not authenticated
        - 403: {"error": "Superuser access not allowed"} - Superuser attempted access
        - 403: {"error": "Admin access required"} - User is not institution admin
    
    @notes:
        - Calculates metrics only for question categories that exist in institution's templates
        - Monthly trends are calculated from January to the month of the latest response
        - Response rates are based on unique students per month
        - Flagged students are determined by their latest survey response
        - Sleep quality: good (1-2), neutral (3), bad (4-5) on Likert scale
        - Stress levels: low (1-2), moderate (3), high (4-5) on Likert scale
        - Support perception: positive responses (1-2) on Likert scale
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    
    if request.user.is_superuser:
        return JsonResponse({"error": "Superuser access not allowed"}, status=403)
    
    if request.user.role != User.Role.INSTITUTION_ADMIN:
        return JsonResponse({"error": "Admin access required"}, status=403)
    
    # Get the institution details of the admin
    institution_details = request.user.institution_details

    # Number of students registered in the university
    num_registered_students = User.objects.filter(role=User.Role.STUDENT, institution_details=institution_details).count()

    num_anonymous_students = AnonymousStudent.objects.filter(survey_template__institution=institution_details).count()

    num_students = num_registered_students+num_anonymous_students

    #responded_students = 0
    # Get all students in the institution
    institution_students = User.objects.filter(role=User.Role.STUDENT, institution_details=institution_details)
    
    anonymous_students = AnonymousStudent.objects.filter(survey_template__institution=institution_details)

    # Initialize list for flagged students
    school_flagged_responses = []
    # ── Latest response per registered student (1 query using Subquery) ──
    latest_registered_response = SurveyResponse.objects.filter(
        student=OuterRef('pk')
    ).order_by('-created')

    registered_with_status = User.objects.filter(
        role=User.Role.STUDENT,
        institution_details=institution_details
    ).annotate(
        has_response=Subquery(latest_registered_response.values('id')[:1]),
        latest_flagged=Subquery(latest_registered_response.values('flagged')[:1])
    )

    registered_responded = registered_with_status.filter(
        has_response__isnull=False
    ).count()

    registered_flagged = list(
        registered_with_status.filter(
            latest_flagged=True
        ).values_list('name', 'email')
    )

    # ── Latest response per anonymous student (1 query using Subquery) ──
    latest_anon_response = SurveyResponse.objects.filter(
        anonymous_student=OuterRef('pk')
    ).order_by('-created')

    anon_with_status = AnonymousStudent.objects.filter(
        survey_template__institution=institution_details
    ).annotate(
        has_response=Subquery(latest_anon_response.values('id')[:1]),
        latest_flagged=Subquery(latest_anon_response.values('flagged')[:1])
    )

    anon_responded = anon_with_status.filter(
        has_response__isnull=False
    ).count()

    anon_flagged = list(
        anon_with_status.filter(
            latest_flagged=True
        ).values_list('name', 'email')
    )

    # ── Combine results ──
    responded_students = registered_responded + anon_responded
    school_flagged_responses = registered_flagged + anon_flagged
    num_flagged_students = len(school_flagged_responses)

    # Number of responses for students registered in the university
    #all_registered_responses = SurveyResponse.objects.filter(student__institution_details=institution_details)
    #all_anonymous_responses = SurveyResponse.objects.filter(anonymous_student__survey_template__institution=institution_details)
    #num_responses = len(all_registered_responses)+len(all_anonymous_responses)
    all_responses = SurveyResponse.objects.filter(
    Q(student__institution_details=institution_details) | 
    Q(anonymous_student__survey_template__institution=institution_details)
    )
    num_responses = all_responses.count()
    
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
    if has_sleep_questions:
        sleep_stats = QuestionResponse.objects.filter(
            question__survey_template__in=survey_templates,
            question__category=QuestionCategory.SLEEP,
            survey_response__in=all_responses,
            likert_value__isnull=False
        ).aggregate(
            good=Count('id', filter=Q(likert_value__lte=2)),
            bad=Count('id', filter=Q(likert_value__gte=4))
        )
        num_good_sleep_quality = sleep_stats['good']
        num_bad_sleep_quality = sleep_stats['bad']

    if has_stress_questions:
        stress_stats = QuestionResponse.objects.filter(
            question__survey_template__in=survey_templates,
            question__category=QuestionCategory.STRESS,
            survey_response__in=all_responses,
            likert_value__isnull=False
        ).aggregate(
            low=Count('id', filter=Q(likert_value__lte=2)),
            moderate=Count('id', filter=Q(likert_value=3)),
            high=Count('id', filter=Q(likert_value__gte=4))
        )
        num_low_stress = stress_stats['low']
        num_moderate_stress = stress_stats['moderate']
        num_high_stress = stress_stats['high']

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
       
            if has_support_questions:
                support_count = QuestionResponse.objects.filter(
                    question__survey_template__in=survey_templates,
                    question__category=QuestionCategory.SUPPORT,
                    survey_response__in=month_responses,
                    likert_value__isnull=False,
                    likert_value__lte=2
                ).count()
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
    """
    Authenticates users and establishes session with secure cookies.
    
    This endpoint handles user authentication by validating email/password credentials,
    creating a session, and setting secure authentication cookies for frontend use.
    
    @params:
        request (HttpRequest): Django HTTP request object
            - method: Must be POST
            - body (JSON): {
                "email": str,     # User's email address
                "password": str   # User's password
            }
    
    @returns:
        JsonResponse: Authentication result with user information and cookies
        
        Success Response (200):
        {
            "success": true,
            "message": "Login successful!",
            "is_admin": bool,              # Whether user is institution admin
            "redirect_path": str           # Suggested redirect path based on user role
        }
        
        Cookies Set on Success:
        - auth_token: Session key (7 days, Lax SameSite)
        - user_email: User's email (7 days, Lax SameSite)
        - is_superuser: "true"/"false" (7 days, Lax SameSite)
        - is_institution_admin: "true"/"false" (7 days, Lax SameSite)
        
        Error Responses:
        - 400: {"error": "No data provided"} - Empty request body
        - 400: {"error": "Email and password required"} - Missing credentials
        - 400: {"error": "Invalid JSON format"} - Malformed JSON
        - 400: {"success": false, "message": "Invalid credentials"} - Authentication failed
        - 405: {"error": "Use POST method"} - Wrong HTTP method
        - 500: {"error": "Server error occurred"} - Internal server error
    
    @notes:
        - Cookie settings use Django settings for domain, security, and SameSite policies
        - Redirect path is "/dashboard/" for admins, "/survey/" for students
        - All cookies expire after 7 days
        - Uses Django's built-in authentication system
    """
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
                    'is_admin': user.role == User.Role.INSTITUTION_ADMIN,
                    'redirect_path': '/dashboard/' if user.role == User.Role.INSTITUTION_ADMIN else '/survey/'
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
                    'true' if user.role == User.Role.INSTITUTION_ADMIN else 'false', 
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
    Registers new student users with institution validation.
    
    This endpoint creates new student accounts after validating institution membership
    through email pattern matching and ensuring the institution exists in the system.
    
    @params:
        request (HttpRequest): Django HTTP request object
            - method: Must be POST
            - data (JSON or form): {
                "institution_name": str,    # Name of the institution
                "name": str,               # Student's full name
                "email": str,              # Student's email address
                "password": str,           # Desired password
                "confirm_password": str    # Password confirmation
            }
    
    @returns:
        Response: Registration result with success/error information
        
        Success Response (201):
        {
            "success": true,
            "message": "Registration successful! Please log in."
        }
        
        Error Responses:
        - 400: {"success": false, "message": "Passwords do not match."}
        - 400: {"success": false, "message": "Email already registered."}
        - 400: {"success": false, "message": "Institution does not exist"}
        - 400: {"success": false, "message": "Email does not match institution's format"}
        - 500: {"success": false, "message": "Registration failed. Please try again."}
    
    @notes:
        - Email must match the institution's regex pattern for validation
        - Creates student users with role=STUDENT
        - Institution must exist in the database before registration
        - Uses case-insensitive regex matching for email validation
        - Automatically associates user with the specified institution
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
            with transaction.atomic():
                student = User.objects.create_student(
                    email=email, 
                    password=password, 
                    institution_details=institution_details, 
                    name=name
                )
                #student.save()
                
                return Response({
                    'success': True,
                    'message': "Registration successful! Please log in."
                }, status=status.HTTP_201_CREATED)
        except IntegrityError:
            return Response({
                'success': False,
                'message': "Registration failed. Email already registered"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            return Response({
                'success': False,
                'message': "Registration failed. Please try again."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["POST"])
def logout_view(request):
    """
    Logs out authenticated users and clears session cookies.
    
    This endpoint terminates the user's session and removes all authentication-related
    cookies to ensure complete logout from the system.
    
    @params:
        request (HttpRequest): Django HTTP request object
            - method: Must be POST
            - user: Must be authenticated (automatic Django middleware)
    
    @returns:
        JsonResponse: Logout confirmation with cleared cookies
        
        Success Response (200):
        {
            "success": true,
            "message": "You have been logged out successfully."
        }
        
        Cookies Cleared:
        - sessionid: Django session cookie
        - auth_token: Custom authentication token
        - user_email: Stored user email
        - is_institution_admin: Admin status flag
        - is_superuser: Superuser status flag
    
    @notes:
        - Always returns success response regardless of authentication status
        - Clears cookies using Django settings for domain configuration
        - Uses Django's built-in logout() function to terminate session
        - Safe to call multiple times or when already logged out
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
    Retrieves survey responses with role-based access control.
    
    This endpoint returns survey responses based on user permissions:
    - Superusers see all responses across all institutions
    - Institution admins see only responses from their institution
    
    @params:
        request (HttpRequest): Django HTTP request object
            - method: Must be GET
            - user: Must be authenticated superuser or institution admin (User.Role.INSTITUTION_ADMIN)
    
    @returns:
        Response: Serialized survey response data
        
        Success Response (200):
        [
            {
                "id": int,
                "student": int|null,           # Student ID (null for anonymous)
                "anonymous_student": int|null, # Anonymous student ID
                "created": str,                # ISO datetime string
                "flagged": bool,               # Whether response is flagged
                "responses": [...],            # Question responses array
                # ... other SurveyResponse fields
            },
            ...
        ]
        
        Error Responses:
        - 400: "Request method not allowed" - Authentication or permission failed
    
    @notes:
        - Includes both registered student and anonymous student responses
        - Institution admins see responses filtered by their institution
        - Uses Q objects to query across student and anonymous_student relationships
        - Returns serialized data using SurveyResponseSerializer
    """
    if request.method == "GET" and request.user.is_authenticated and (request.user.is_superuser or request.user.role == User.Role.INSTITUTION_ADMIN):
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
    Retrieves flagged survey responses with role-based filtering.
    
    This endpoint returns only survey responses that have been flagged as concerning,
    with access control based on user permissions.
    
    @params:
        request (HttpRequest): Django HTTP request object
            - method: Must be GET
            - user: Must be authenticated superuser or institution admin (User.Role.INSTITUTION_ADMIN)
    
    @returns:
        Response: Serialized flagged survey response data
        
        Success Response (200):
        [
            {
                "id": int,
                "student": int|null,           # Student ID (null for anonymous)
                "anonymous_student": int|null, # Anonymous student ID
                "created": str,                # ISO datetime string
                "flagged": true,               # Always true for this endpoint
                "responses": [...],            # Question responses array
                # ... other SurveyResponse fields
            },
            ...
        ]
        
        Error Responses:
        - 400: "Request method not allowed" - Authentication or permission failed
    
    @notes:
        - Only returns responses where flagged=True
        - Superusers see all flagged responses across institutions
        - Institution admins see only flagged responses from their institution
        - Includes both registered and anonymous student flagged responses
    """
    if request.method == "GET" and request.user.is_authenticated and (request.user.is_superuser or request.user.role == User.Role.INSTITUTION_ADMIN):
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
    Retrieves student information with role-based access control.
    
    This endpoint returns both registered and anonymous students based on user permissions,
    providing a comprehensive view of all students in the system or institution.
    
    @params:
        request (HttpRequest): Django HTTP request object
            - method: Must be GET
            - user: Must be authenticated superuser or institution admin (User.Role.INSTITUTION_ADMIN)
    
    @returns:
        Response: Combined registered and anonymous student data
        
        Success Response (200):
        {
            "registered_students": [
                {
                    "id": int,
                    "email": str,
                    "name": str,
                    "institution_details": int,    # Institution ID
                    "is_student": true,
                    "date_joined": str,            # ISO datetime string
                    # ... other User fields
                },
                ...
            ],
            "anonymous_students": [
                {
                    "id": int,
                    "name": str|null,              # May be null for anonymous
                    "email": str,
                    "survey_template": int,        # Template ID
                    "created": str,                # ISO datetime string
                    # ... other AnonymousStudent fields
                },
                ...
            ]
        }
        
        Error Responses:
        - 400: "Request method not allowed" - Authentication or permission failed
    
    @notes:
        - Separates registered users (User model) from anonymous students (AnonymousStudent model)
        - Superusers see all students across all institutions
        - Institution admins see only students from their institution
        - Uses separate serializers for different student types
        - Anonymous students are linked to institutions through survey templates
    """
    if request.method == "GET" and request.user.is_authenticated and (request.user.is_superuser or request.user.role == User.Role.INSTITUTION_ADMIN):
        if request.user.is_superuser:
            # Superuser sees all students
            all_students = User.objects.filter(role=User.Role.STUDENT)
            all_anonymous_students = AnonymousStudent.objects.all()
        else:
            # Institution admin sees only students from their institution
            all_students = User.objects.filter(
                role=User.Role.STUDENT,
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
    
    if not (request.user.is_superuser or request.user.role == User.Role.INSTITUTION_ADMIN):
        return JsonResponse({"error": "Admin access required"}, status=403)
    
    try:
        flagged_registered_students = []
        flagged_anonymous_students = []
        
        # ── Registered students ──
        latest_response = SurveyResponse.objects.filter(
            student=OuterRef('pk')
        ).order_by('-created')

        students_qs = User.objects.filter(role=User.Role.STUDENT)
        if not request.user.is_superuser:
            students_qs = students_qs.filter(
                institution_details=request.user.institution_details
            )

        flagged_registered = students_qs.annotate(
            latest_flagged=Subquery(latest_response.values('flagged')[:1]),
            latest_response_date=Subquery(latest_response.values('created')[:1]),
            latest_response_id=Subquery(latest_response.values('id')[:1])
        ).filter(
            latest_flagged=True
        ).select_related('institution_details')

        flagged_registered_students = [{
            "id": s.id,
            "name": s.name,
            "email": s.email,
            "institution_id": s.institution_details.id if s.institution_details else None,
            "institution_name": s.institution_details.institution_name if s.institution_details else None,
            "latest_response_date": s.latest_response_date,
            "latest_response_id": s.latest_response_id
        } for s in flagged_registered]

        # ── Anonymous students ──
        latest_anon_response = SurveyResponse.objects.filter(
            anonymous_student=OuterRef('pk')
        ).order_by('-created')

        anon_qs = AnonymousStudent.objects.all()
        if not request.user.is_superuser:
            anon_qs = anon_qs.filter(
                survey_template__institution=request.user.institution_details
            )

        flagged_anon = anon_qs.annotate(
            latest_flagged=Subquery(latest_anon_response.values('flagged')[:1]),
            latest_response_date=Subquery(latest_anon_response.values('created')[:1]),
            latest_response_id=Subquery(latest_anon_response.values('id')[:1])
        ).filter(
            latest_flagged=True
        ).select_related('survey_template__institution')

        flagged_anonymous_students = [{
            "email": s.email,
            "name": s.name,
            "institution_id": s.survey_template.institution.id if s.survey_template else None,
            "institution_name": s.survey_template.institution.institution_name if s.survey_template else None,
            "survey_template_id": s.survey_template.id if s.survey_template else None,
            "latest_response_date": s.latest_response_date,
            "latest_response_id": s.latest_response_id,
            "created_at": s.created_at
        } for s in flagged_anon]
        
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
    Retrieves all institutions in the database.
    
    This endpoint returns a list of all registered institutions available in the system.
    
    @params:
        request (HttpRequest): Django HTTP request object
            - method: Must be GET
    
    @returns:
        Response: Serialized institution data
        
        Success Response (200):
        [
            {
                "id": int,
                "institution_name": str,
                "institution_regex_pattern": str,
                # ... other Institution fields
            },
            ...
        ]
        
        Error Responses:
        - 400: "Request method not allowed" - Wrong HTTP method
    
    @notes:
        - No authentication required - public endpoint
        - Returns all institutions without filtering
        - Used for registration form population
    """
    if request.method == "GET":
        all_institutions = Institution.objects.all()
        institution_serializer = InstitutionSerializer(all_institutions, many=True)
        return Response(institution_serializer.data)
    
    else:
        return HttpResponseBadRequest("Request method not allowed")

@api_view(["GET", "POST", "DELETE"])
def survey_templates_view(request):
    """
    Manages survey templates with full CRUD operations.
    
    This endpoint allows institution admins to list, create, and delete survey templates
    for their institution with proper access control.
    
    @params:
        request (HttpRequest): Django HTTP request object
            - method: GET, POST, or DELETE
            - user: Must be authenticated institution admin
            - data (for POST/DELETE): JSON payload with operation-specific fields
    
    @returns:
        JsonResponse: Operation result with template data or confirmation
        
        GET Success Response (200):
        {
            "success": true,
            "templates": [
                {
                    "id": int,
                    "institution": int,
                    "hash_link": str,
                    "used": bool,
                    "created": str,
                    # ... other SurveyTemplate fields
                },
                ...
            ]
        }
        
        POST Success Response (200):
        {
            "success": true,
            "message": "Survey template created",
            "id": int,
            "hash_link": str
        }
        
        DELETE Success Response (200):
        {
            "success": true,
            "message": "Template deleted"
        }
        
        Error Responses:
        - 403: {"success": false, "error": "Permission denied"} - Not institution admin
        - 400: {"success": false, "error": "Template ID is required"} - Missing template_id for DELETE
        - 404: Template not found or doesn't belong to institution
        - 500: {"success": false, "error": "..."} - Server error
    
    @notes:
        - GET: Lists all templates for admin's institution
        - POST: Creates new template automatically associated with admin's institution
        - DELETE: Requires template_id in request data, cascades to delete questions
        - All operations restricted to institution admin's own templates
    """
    if not request.user.is_authenticated or request.user.role != User.Role.INSTITUTION_ADMIN:
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
    Manages survey questions for a specific template with full CRUD operations.
    
    This endpoint allows institution admins (User.Role.INSTITUTION_ADMIN) to list, create, and delete questions
    within their survey templates with proper validation and ordering.
    
    @params:
        request (HttpRequest): Django HTTP request object
            - method: GET, POST, or DELETE
            - user: Must be authenticated institution admin (User.Role.INSTITUTION_ADMIN)
        template_id (int): ID of the survey template to manage
        
        POST data (JSON):
        {
            "question_text": str,          # Question content
            "question_type": str,          # QuestionType enum value
            "question_category": str,      # QuestionCategory enum value
            "answer_choices": str|null     # JSON string for Likert choices
        }
        
        DELETE data (JSON):
        {
            "question_id": int             # ID of question to delete
        }
    
    @returns:
        JsonResponse: Operation result with question data or confirmation
        
        GET Success Response (200):
        {
            "success": true,
            "questions": [
                {
                    "id": int,
                    "question_text": str,
                    "question_type": str,
                    "category": str,
                    "order": int,
                    "answer_choices": str|null,
                    # ... other SurveyQuestion fields
                },
                ...
            ]
        }
        
        POST Success Response (200):
        {
            "success": true,
            "message": "Question added",
            "question": { /* serialized question data */ }
        }
        
        DELETE Success Response (200):
        {
            "success": true,
            "message": "Question deleted"
        }
        
        Error Responses:
        - 403: {"success": false, "error": "Permission denied"} - Not institution admin
        - 403: {"success": false, "error": "You can only manage your institution's surveys"}
        - 404: Template not found
        - 400: {"success": false, "error": "Question ID is required"} - Missing question_id for DELETE
        - 500: {"success": false, "error": "..."} - Server error
    
    @notes:
        - GET: Returns questions ordered by 'order' field
        - POST: Auto-assigns next available order number, defaults to LIKERT/GENERAL
        - DELETE: Automatically reorders remaining questions after deletion
        - Template ownership validated against admin's institution
        - Supports both Likert scale and text question types
    """
    if not request.user.is_authenticated or request.user.role != User.Role.INSTITUTION_ADMIN:
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
            with transaction.atomic():
                locked_qs = list(
                    SurveyQuestion.objects.filter(survey_template=template).select_for_update()
                )
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
                #if data.get('answer_choices') and data.get('question_type') == QuestionType.LIKERT:
                #    new_question.answer_choices = data.get('answer_choices')
                
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
            with transaction.atomic():
                
                locked_qs = list(
                    SurveyQuestion.objects.filter(survey_template=template).select_for_update()
                )

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
    """
    Activates a specific survey template for institutional use.
    
    This endpoint allows institution admins to designate which survey template
    should be actively used for student surveys, deactivating all others.
    
    @params:
        request (HttpRequest): Django HTTP request object
            - method: Must be POST
            - user: Must be authenticated institution admin
        template_id (int): ID of the survey template to activate
    
    @returns:
        JsonResponse: Activation result
        
        Success Response (200):
        {
            "success": true
        }
        
        Error Responses:
        - 403: {"success": false, "error": "Unauthorized"} - Not institution admin
        - 404: Template not found or doesn't belong to institution
        - 500: {"success": false, "error": "..."} - Server error
    
    @notes:
        - Only one template per institution can be active at a time
        - Automatically deactivates all other templates for the institution
        - Template must belong to the admin's institution
        - Used template becomes the default for student surveys
    """
    if not request.user.is_authenticated or request.user.role != User.Role.INSTITUTION_ADMIN:
        return JsonResponse({"success": False, "error": "Unauthorized"})

    try:
        with transaction.atomic():
            SurveyTemplate.objects.filter(
            institution=request.user.institution_details
            ).select_for_update().update(used=False)

            # Get the template to activate
            template = get_object_or_404(SurveyTemplate.objects.select_for_update(), id=template_id, institution=request.user.institution_details)
            
            # Activate the selected template
            template.used = True
            template.save()
            
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})

# Modify the existing survey_view to use the 'used' field
def get_active_template(institution):
    """
    Retrieves the active survey template for an institution.
    
    This helper function finds the currently active survey template for an institution,
    with fallback logic to automatically activate the oldest template if none is marked as used.
    
    @params:
        institution (Institution): Institution object to find template for
    
    @returns:
        SurveyTemplate|None: Active template object or None if no templates exist
    
    @notes:
        - First tries to find template with used=True
        - Falls back to template with lowest ID if no active template
        - Automatically marks fallback template as used=True
        - Returns None if institution has no templates
    """
    with transaction.atomic():
        # Try to get the used template first
        template = SurveyTemplate.objects.select_for_update().filter(institution=institution, used=True).first()
        
        # If no template is marked as used, get the one with minimal ID
        if not template:
            template = SurveyTemplate.objects.select_for_update().filter(institution=institution).order_by('id').first()
            if template:
                # Automatically mark this template as used
                template.used = True
                template.save()
    
    return template

@api_view(["POST"])
def survey_autosave(request):
    """
    Saves survey progress to cache for authenticated users.
    
    This endpoint allows students to save their survey progress temporarily,
    enabling them to resume later without losing their responses.
    
    @params:
        request (HttpRequest): Django HTTP request object
            - method: Must be POST
            - user: Must be authenticated
            - data (JSON): {
                "template_id": int,        # Survey template ID
                "answers": dict            # Question ID -> response mapping
            }
    
    @returns:
        JsonResponse: Save operation result
        
        Success Response (200):
        {
            "success": true,
            "message": "Progress saved"
        }
        
        Error Responses:
        - 200: {"success": false, "message": "User not authorized"} - Not authenticated
        - 200: {"success": false, "message": "Error: Wrong template id"} - Missing template_id
        - 404: {"success": false, "message": "Invalid survey template"} - Template not found
        - 200: {"success": false, "message": "Failed to save progress"} - Cache error
    
    @notes:
        - Data cached for 30 minutes (1800 seconds)
        - Cache key format: "survey_autosave_{email}_{template_id}"
        - Includes timestamp of last save
        - Overwrites previous autosave data for same user/template
        - Uses Django cache framework for temporary storage
    """
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
    """
    Loads previously saved survey progress from cache.
    
    This endpoint retrieves autosaved survey data for authenticated users,
    allowing them to resume their survey from where they left off.
    
    @params:
        request (HttpRequest): Django HTTP request object
            - method: Must be GET
            - user: Must be authenticated
        template_id (int): Survey template ID to load progress for
    
    @returns:
        JsonResponse: Load operation result with saved data
        
        Success Response (200):
        {
            "success": true,
            "saved_data": {
                "template_id": int,
                "student_name": str,
                "school_email": str,
                "last_saved": str,         # ISO datetime string
                "answers": dict            # Question ID -> response mapping
            }
        }
        
        Error Responses:
        - 200: {"success": false, "message": "User not authorized"} - Not authenticated
        - 200: {"success": false, "message": "No autosaved data found"} - No cached data
        - 200: {"success": false, "message": "Corrupted save data. Please press the clear button"} - Invalid JSON
        - 200: {"success": false, "message": "Failed to load autosave"} - Cache error
    
    @notes:
        - Cache key format: "survey_autosave_{email}_{template_id}"
        - Automatically clears corrupted cache data
        - Returns user's name and email along with answers
        - Data expires after 30 minutes of inactivity
    """
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
    """
    Clears saved survey progress from cache.
    
    This endpoint allows authenticated users to manually delete their autosaved
    survey progress, useful when starting fresh or after successful submission.
    
    @params:
        request (HttpRequest): Django HTTP request object
            - method: Must be DELETE
            - user: Must be authenticated
        template_id (int): Survey template ID to clear progress for
    
    @returns:
        JsonResponse: Clear operation result
        
        Success Response (200):
        {
            "success": true,
            "message": "Autosave data cleared"
        }
        
        Error Responses:
        - 200: {"success": false, "message": "User not authorized"} - Not authenticated
        - 200: {"success": false, "message": "Failed to clear draft"} - Cache error
    
    @notes:
        - Cache key format: "survey_autosave_{email}_{template_id}"
        - Safe to call even if no autosave data exists
        - Typically called after successful survey submission
        - Immediately removes data from cache
    """
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
