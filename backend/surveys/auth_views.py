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
from django.db import connection, transaction, IntegrityError
from tenants.models import EmailTenantMapping, Institution

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
            
            # Resolve tenant before authenticating — User lives in tenant schema
            try:
                mapping = EmailTenantMapping.objects.get(email=email)
                tenant = Institution.objects.get(schema_name=mapping.schema_name)
                connection.set_tenant(tenant)
            except (EmailTenantMapping.DoesNotExist, Institution.DoesNotExist):
                connection.set_schema_to_public()

            user = authenticate(request, email=email, password=password)

            if user is not None:
                login(request, user)
                request.session['_tenant_schema'] = connection.schema_name
                
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
        
        # Institution lookup runs on public schema (Institution is SHARED)
        institution_details = Institution.objects.filter(institution_name=institution_name)
        if not institution_details.exists():
            return Response({
                'success': False,
                'message': "Institution does not exist"
            }, status=status.HTTP_400_BAD_REQUEST)

        institution_details = institution_details.first()
        match_object = re.fullmatch(institution_details.institution_regex_pattern, email, re.IGNORECASE)
        if not match_object:
            return Response({
                'success': False,
                'message': "Email does not match institution's format"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Set tenant schema before creating User (User lives per-tenant)
        connection.set_tenant(institution_details)

        try:
            with transaction.atomic():
                student = User.objects.create_student(
                    email=email,
                    password=password,
                    institution_details=institution_details,
                    name=name
                )

                # Create public-schema mapping so login can find the tenant
                connection.set_schema_to_public()
                EmailTenantMapping.objects.create(
                    email=email,
                    schema_name=institution_details.schema_name
                )

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