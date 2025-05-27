import logging
import calendar
import re
from .models import SurveyResponse, User, Institution, SurveyTemplate, SurveyQuestion, QuestionResponse, QuestionType, QuestionCategory
from .serializers import SurveyResponseSerializer, UserSerializer, InstitutionSerializer, SurveyTemplateSerializer, SurveyQuestionSerializer
from django.shortcuts import render, redirect
from django.utils import timezone
from django.http import JsonResponse, HttpResponseBadRequest, QueryDict
from django.contrib.auth import authenticate, login, logout
from django.urls import reverse
from django.contrib import messages
from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.shortcuts import get_object_or_404
import json

# Use a single logger configuration
logger = logging.getLogger("surveys")

def index_view(request):
    """
    index_view returns the home page
    """
    if request.method == "GET":
        return render(request, 'index.html')
   
def demo_survey_view(request):
    """
    demo_survey_view renders a sample survey response to visitors
    """
    if request.method == "GET":
        return render(request, "survey.html")


@api_view(["GET", "POST"])
def survey_view(request, hash_link=None):
    """
    survey_view allows students to access the survey page
    and save survey responses
    """
    if request.method == 'GET':
        context = {}
        survey_template = None
        
        # If hash_link is provided, try to get the template by hash_link
        if hash_link:
            try:
                survey_template = SurveyTemplate.objects.get(hash_link=hash_link)
                context["survey_template_id"] = survey_template.id
            except SurveyTemplate.DoesNotExist:
                pass
        
        # Check if user is a developer/wants to just look at the form
        if request.user.is_authenticated and request.user.is_superuser:
            context.update({
                "student_email": "",
                "student_name": ""
            })
        
        # Check if the user is a student
        elif request.user.is_authenticated and not request.user.is_institution_admin:
            # Extract data for the logged in student
            context.update({
                "student_email": request.user.email,
                "student_name": request.user.name
            })
            
            # If no template was found by hash_link, try to get one by institution
            if not survey_template and request.user.institution_details:
                survey_template = SurveyTemplate.objects.filter(institution=request.user.institution_details).first()
                if survey_template:
                    context["survey_template_id"] = survey_template.id
        
        # Check if the user is an admin
        elif request.user.is_authenticated and request.user.is_institution_admin:
            # Redirect to the dashboard page if the user is an admin
            return redirect("dashboard")
        else:
            # Redirect to the login page if the user has not logged in
            return redirect("login")

        return render(request, 'survey.html', context=context)
    
    elif request.method == 'POST':
        # Check if a valid user is submitting the response
        if not request.user.is_authenticated:
            return JsonResponse({"success": False, "error": f"Please login to the application to submit a survey response"})
        
        # Get the survey template - either from request or use a default
        survey_template_id = request.data.get('survey_template_id')
        if not survey_template_id:
            # You might want to get a default template based on the user's institution
            if request.user.institution_details:
                try:
                    survey_template = SurveyTemplate.objects.filter(institution=request.user.institution_details).first()
                    if not survey_template:
                        return JsonResponse({"success": False, "error": "No survey template found for your institution"})
                except Exception as e:
                    return JsonResponse({"success": False, "error": f"Error finding survey template: {str(e)}"})
            else:
                return JsonResponse({"success": False, "error": "No institution associated with user and no survey template specified"})
        else:
            try:
                survey_template = SurveyTemplate.objects.get(id=survey_template_id)
            except Exception as e:
                return JsonResponse({"success": False, "error": f"Invalid survey template: {str(e)}"})

        # Get all questions for this template
        questions = SurveyQuestion.objects.filter(survey_template=survey_template)
        if not questions.exists():
            return JsonResponse({"success": False, "error": "No questions found in the survey template"})
        
        # Check if all questions have responses
        missing_responses = []
        for question in questions:
            question_id = str(question.id)
            if question_id not in request.data:
                missing_responses.append(question.question_text[:30] + "...")
        
        if missing_responses:
            return JsonResponse({"success": False, "error": f"Missing responses for questions: {', '.join(missing_responses)}"})

        # Important: You can't return a @api_view within another @api_view
        return _handle_student_responses(request, survey_template, questions)


def _handle_student_responses(request, survey_template, questions):
    """
    A function that serializes student responses, returns proper Json responses and saves them to the database.
    """
    # Get the email and validate it ends with .edu
    school_email = request.user.email
    if 'school_email' in request.data:
        school_email = request.data.get('school_email')
    
    # Check if email ends with .edu
    if not school_email.lower().endswith('.edu'):
        return JsonResponse({
            "success": False,
            "message": "Please use a valid .edu email address.",
            "error": "Invalid email domain. Only .edu email addresses are accepted."
        })
    
    # Save the student response
    student = request.user
    
    # Update student name if provided
    if 'student_name' in request.data and not student.name:
        student.name = request.data['student_name']
        student.save()
    
    # Create the survey response
    try:
        survey_response = SurveyResponse.objects.create(
            student=student,
            survey_template=survey_template,
            flagged=False  # Will update this after checking responses
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
        
        # Return success response
        response_data = {
            "success": True,
            "message": "Thank you for your honest response! Your input makes a difference.",
            "redirect_url": reverse('index'),
            "data": SurveyResponseSerializer(survey_response).data,
        }
        return JsonResponse(response_data)
    
    except Exception as e:
        # Return error response if any errors occur
        logger.error("Error saving survey response: %s", str(e))
        return JsonResponse({
            "success": False,
            "message": "There was an error with your submission.",
            "error": str(e)
        })

@api_view(["GET"])
def get_user_survey_questions(request):
    """
    API endpoint to get survey questions for the current user based on their institution
    """
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required"})
    
    survey_template = None
    
    # If user is a student, get template by institution
    if not request.user.is_institution_admin and not request.user.is_superuser:
        if request.user.institution_details:
            survey_template = SurveyTemplate.objects.filter(
                institution=request.user.institution_details
            ).first()
    
    # If user is a superuser, get any template (for testing)
    elif request.user.is_superuser:
        survey_template = SurveyTemplate.objects.first()
    
    if not survey_template:
        return JsonResponse({
            "success": False, 
            "error": "No survey template found for your institution"
        })
    
    # Get all questions for this template
    questions = SurveyQuestion.objects.filter(survey_template=survey_template).order_by('order')
    
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


def dashboard_view(request):
    """
    dashboard_view returns the dashboard page for a particular university.
    """
    if request.method != "GET":
        return HttpResponseBadRequest("Bad request: resource not found/bad request")
    
    if not request.user.is_authenticated:
        return redirect("login")
    
    if request.user.is_superuser:
        return redirect(reverse("admin:index"))
    
    if not request.user.is_institution_admin:
        return HttpResponseBadRequest("Bad request: resource not found/bad request")
    
    # Get the institution details of the admin
    institution_details = request.user.institution_details

    # Number of students registered in the university
    num_students = len(User.objects.filter(is_student=True, institution_details=institution_details))

    responded_students = 0
    # Get all students in the institution
    institution_students = User.objects.filter(is_student=True, institution_details=institution_details)
    
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

    # Number of responses for students registered in the university
    all_responses = SurveyResponse.objects.filter(student__institution_details=institution_details)
    num_responses = len(all_responses)

    
    # Number of students registered in the university and marked as flagged
    num_flagged_students = all_responses.values('student').distinct().count()
    
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
            unique_students_responded = month_responses.values('student').distinct().count()
            
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
                response = redirect('dashboard')
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

        # Check if the user has been already authenticated
        if request.user.is_authenticated:
            
            # Check if the user is an admin
            user = User.objects.filter(email = request.user.email).first()
            if user.is_institution_admin:
                return redirect("dashboard")
            else:
                return redirect("survey")

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
        match_object = re.fullmatch(institution_details.institution_regex_pattern, email, re.IGNORECASE)
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


# NOTE: API views are WIP. Need to add parameters for filtering db records
@api_view(['GET'])
def student_response_view(request):
    """
    student_response_view is an API view that returns all survey responses
    saved in the database
    """
    if request.method == "GET" and request.user.is_authenticated and request.user.is_superuser:
        survey_responses = SurveyResponse.objects.all()
        survey_response_serializer = SurveyResponseSerializer(survey_responses, many=True)
        return Response(survey_response_serializer.data)
    
    else:
        return HttpResponseBadRequest("Request method not allowed")


@api_view(["GET"])
def flagged_students_view(request):
    """
    flagged_students_view is an API view that returns all flagged students
    in the database
    """
    if request.method == "GET" and request.user.is_authenticated and request.user.is_superuser:
        flagged_students = SurveyResponse.objects.filter(flagged=True)
        flagged_students_serializer = SurveyResponseSerializer(flagged_students, many=True)
        return Response(flagged_students_serializer.data)
    
    else:
        return HttpResponseBadRequest("Request method not allowed")
    

@api_view(["GET"])
def students_view(request):
    """
    students_view is an API view that returns all students
    in the database
    """
    if request.method == "GET" and request.user.is_authenticated and request.user.is_superuser:
        all_students = User.objects.filter(is_student=True)
        user_serializer = UserSerializer(all_students, many=True)
        return Response(user_serializer.data)
    
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
