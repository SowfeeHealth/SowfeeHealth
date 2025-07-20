from django.urls import path
from django.contrib.auth.decorators import login_required
from . import views

urlpatterns = [
    # url for csrf
    path('api/csrf/', views.set_csrf_token, name='set_csrf_token'),
    # URLs for user management
    path('api/user/', views.user_view, name='user-api'),
    
    # URLs for student responses and flagged students API
    path("api/student-responses/", views.student_response_view, name="student-responses-api"),
    path("api/flagged-responses/", views.flagged_responses_view, name="flagged-responses-api"),
    path('api/flagged-students/', views.flagged_students_view, name='flagged-students'),
    path('api/students/', views.students_view, name='students-api'),
    path('api/institutions/', views.institutions_view, name='institutions-api'),
    
    # Add new URLs for survey management
    path('api/survey-templates/', views.survey_templates_view, name='survey-templates-api'),
    path('api/survey-templates/<int:template_id>/questions/', views.survey_questions_view, name='survey-questions-api'),
    path('api/admin/survey-templates/', views.survey_templates_admin_view, name='survey-templates-admin'),
    path('api/get-user-survey-questions/', views.get_user_survey_questions, name='get-user-survey-questions'),
    path('api/survey-templates/<int:template_id>/use/', views.use_template, name='use_template'),
    path('api/dashboard/', views.dashboard_api, name='dashboard-api'),
    
    # University-specific and hash link survey URLs
    path('api/survey/link/<uuid:hash_link>/', views.survey_view, name='hashed-survey'),
    path('api/get-user-survey-questions/<uuid:hash_link>/', views.get_user_survey_questions, name='get-user-survey-questions-hash'),

    
    # Keep your other existing URLs
    path('api/survey/', views.survey_view, name='survey'),
    path('api/login/', views.login_view, name='login'),
    path("api/register/", views.register_view, name="register"),
    path("api/logout/", views.logout_view, name="logout"),
    path("api/demo-survey/", views.demo_survey_view, name="demo-survey"),
]