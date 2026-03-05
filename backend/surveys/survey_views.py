
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

logger = logging.getLogger("surveys")

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
