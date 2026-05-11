import logging
import calendar
import re
from .models import SurveyResponse, User, AnonymousStudent, SurveyTemplate, SurveyQuestion, QuestionResponse, QuestionType, QuestionCategory
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
from django.db import connection, transaction, IntegrityError
from django_tenants.utils import schema_context
from tenants.models import SurveyHashLookup, Institution

logger = logging.getLogger("surveys")

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
    
    # Schema isolation: all queries below are scoped to the current tenant schema
    num_registered_students = User.objects.filter(role=User.Role.STUDENT).count()
    num_anonymous_students = AnonymousStudent.objects.count()
    num_students = num_registered_students + num_anonymous_students

    # ── Latest response per registered student (1 query using Subquery) ──
    latest_registered_response = SurveyResponse.objects.filter(
        student=OuterRef('pk')
    ).order_by('-created')

    registered_with_status = User.objects.filter(
        role=User.Role.STUDENT,
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

    anon_with_status = AnonymousStudent.objects.annotate(
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

    # ── Latest responses only (for sleep/stress per-student metrics) ──
    latest_response_ids = list(
        registered_with_status.filter(has_response__isnull=False)
        .values_list('has_response', flat=True)
    ) + list(
        anon_with_status.filter(has_response__isnull=False)
        .values_list('has_response', flat=True)
    )
    latest_responses = SurveyResponse.objects.filter(id__in=latest_response_ids)

    # Number of responses for students registered in the university
    #all_registered_responses = SurveyResponse.objects.filter(student__institution_details=institution_details)
    #all_anonymous_responses = SurveyResponse.objects.filter(anonymous_student__survey_template__institution=institution_details)
    #num_responses = len(all_registered_responses)+len(all_anonymous_responses)
    all_responses = SurveyResponse.objects.all()
    num_responses = all_responses.count()
    
    # Number of students registered in the university and marked as flagged
    num_flagged_students = len(school_flagged_responses)
    
    # Get all survey templates for this institution
    survey_templates = SurveyTemplate.objects.all()

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
            survey_response__in=latest_responses,
            likert_value__isnull=False
        ).aggregate(
            good=Count('id', filter=Q(likert_value__lte=2)),
            bad=Count('id', filter=Q(likert_value__gte=3))
        )
        num_good_sleep_quality = sleep_stats['good']
        num_bad_sleep_quality = sleep_stats['bad']

    if has_stress_questions:
        stress_stats = QuestionResponse.objects.filter(
            question__survey_template__in=survey_templates,
            question__category=QuestionCategory.STRESS,
            survey_response__in=latest_responses,
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
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    if request.user.is_superuser:
        return JsonResponse({"error": "Superuser access not allowed"}, status=403)
    if request.user.role != User.Role.INSTITUTION_ADMIN:
        return JsonResponse({"error": "Admin access required"}, status=403)

    survey_responses = SurveyResponse.objects.all()
    survey_response_serializer = SurveyResponseSerializer(survey_responses, many=True)
    return Response(survey_response_serializer.data)

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
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    if request.user.is_superuser:
        return JsonResponse({"error": "Superuser access not allowed"}, status=403)
    if request.user.role != User.Role.INSTITUTION_ADMIN:
        return JsonResponse({"error": "Admin access required"}, status=403)

    flagged_responses = SurveyResponse.objects.filter(flagged=True)
    flagged_responses_serializer = SurveyResponseSerializer(flagged_responses, many=True)
    return Response(flagged_responses_serializer.data)

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
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    if request.user.is_superuser:
        return JsonResponse({"error": "Superuser access not allowed"}, status=403)
    if request.user.role != User.Role.INSTITUTION_ADMIN:
        return JsonResponse({"error": "Admin access required"}, status=403)

    all_students = User.objects.filter(role=User.Role.STUDENT)
    all_anonymous_students = AnonymousStudent.objects.all()

    user_serializer = UserSerializer(all_students, many=True)
    anonymous_serializer = AnonymousStudentSerializer(all_anonymous_students, many=True)

    response_data = {
        "registered_students": user_serializer.data,
        "anonymous_students": anonymous_serializer.data
    }

    return Response(response_data)

@api_view(["GET"])
def flagged_students_view(request):
    """
    flagged_students_view returns all students (registered and anonymous) whose latest survey response is flagged.
    Only returns unique students, not all their responses.
    
    Access: Institution admins see their institution's students, superusers see all.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    if request.user.is_superuser:
        return JsonResponse({"error": "Superuser access not allowed"}, status=403)
    if request.user.role != User.Role.INSTITUTION_ADMIN:
        return JsonResponse({"error": "Admin access required"}, status=403)

    try:
        flagged_registered_students = []
        flagged_anonymous_students = []

        # ── Registered students ──
        latest_response = SurveyResponse.objects.filter(
            student=OuterRef('pk')
        ).order_by('-created')

        flagged_registered = User.objects.filter(role=User.Role.STUDENT).annotate(
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

        flagged_anon = AnonymousStudent.objects.annotate(
            latest_flagged=Subquery(latest_anon_response.values('flagged')[:1]),
            latest_response_date=Subquery(latest_anon_response.values('created')[:1]),
            latest_response_id=Subquery(latest_anon_response.values('id')[:1])
        ).filter(
            latest_flagged=True
        )

        tenant = connection.tenant
        flagged_anonymous_students = [{
            "email": s.email,
            "name": s.name,
            "institution_id": tenant.id,
            "institution_name": tenant.institution_name,
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
        templates = SurveyTemplate.objects.all()
        serializer = SurveyTemplateSerializer(templates, many=True)
        return JsonResponse({"success": True, "templates": serializer.data})
    
    elif request.method == "POST":
        # Create a new survey template
        try:
            new_template = SurveyTemplate.objects.create()
            with schema_context('public'):
                tenant = Institution.objects.get(schema_name=connection.schema_name)
                SurveyHashLookup.objects.create(
                    hash_link=new_template.hash_link,
                    tenant=tenant,
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
            with schema_context('public'):
                SurveyHashLookup.objects.filter(hash_link=template.hash_link).delete()
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
    
    template = get_object_or_404(SurveyTemplate, id=template_id)
    
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
            SurveyTemplate.objects.select_for_update().update(used=False)

            template = get_object_or_404(SurveyTemplate.objects.select_for_update(), id=template_id)
            
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
        template = SurveyTemplate.objects.select_for_update().filter(used=True).first()

        if not template:
            template = SurveyTemplate.objects.select_for_update().order_by('id').first()
            if template:
                # Automatically mark this template as used
                template.used = True
                template.save()
    
    return template