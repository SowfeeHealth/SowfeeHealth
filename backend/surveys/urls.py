from django.urls import path, include
from django.contrib.auth.decorators import login_required
from .auth_views import set_csrf_token, user_view, login_view, register_view, logout_view
from .survey_views import demo_survey_view, survey_view, get_user_survey_questions, survey_autosave, survey_autosave_load, survey_autosave_clear
from .admin_views import dashboard_api, student_response_view, flagged_responses_view, students_view, flagged_students_view, institutions_view, survey_templates_view, survey_questions_view, use_template

urlpatterns = [
    # url for csrf
    path('api/csrf/', set_csrf_token, name='set_csrf_token'),
    # URLs for user management
    path('api/user/', user_view, name='user-api'),
    
    # URLs for student responses and flagged students API
    path("api/student-responses/", student_response_view, name="student-responses-api"),
    path("api/flagged-responses/", flagged_responses_view, name="flagged-responses-api"),
    path('api/flagged-students/', flagged_students_view, name='flagged-students'),
    path('api/students/', students_view, name='students-api'),
    path('api/institutions/', institutions_view, name='institutions-api'),
    
    # Add new URLs for survey management
    path('api/survey-templates/', survey_templates_view, name='survey-templates-api'),
    path('api/survey-templates/<int:template_id>/questions/', survey_questions_view, name='survey-questions-api'),
    #path('api/admin/survey-templates/', survey_templates_admin_view, name='survey-templates-admin'),
    path('api/get-user-survey-questions/', get_user_survey_questions, name='get-user-survey-questions'),
    path('api/survey-templates/<int:template_id>/use/', use_template, name='use_template'),
    path('api/dashboard/', dashboard_api, name='dashboard-api'),
    
    # University-specific and hash link survey URLs
    path('api/survey/link/<uuid:hash_link>/', survey_view, name='hashed-survey'),
    path('api/get-user-survey-questions/<uuid:hash_link>/', get_user_survey_questions, name='get-user-survey-questions-hash'),

    # Auto saving survey responses
    path('api/autosave/', survey_autosave, name='autosave-survey'),
    path('api/autosave/load/<int:template_id>/', survey_autosave_load, name='autosave-survey-load'),
    path('api/autosave/clear/<int:template_id>/', survey_autosave_clear, name='survey-autosave-clear'),
    
    # Keep your other existing URLs
    path('api/survey/', survey_view, name='survey'),
    path('api/login/', login_view, name='login'),
    path("api/register/", register_view, name="register"),
    path("api/logout/", logout_view, name="logout"),
    path("api/demo-survey/", demo_survey_view, name="demo-survey"),
    path('api/chat/', include('chat.urls')),
]