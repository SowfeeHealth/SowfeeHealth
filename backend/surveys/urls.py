from django.urls import path
from django.contrib.auth.decorators import login_required
from . import views

urlpatterns = [
    # Keep your existing URLs
    path("api/student-responses/", views.student_response_view, name="student-responses-api"),
    path("api/flagged-students/", views.flagged_students_view, name="flagged-students-api"),
    path('api/students/', views.students_view, name='students-api'),
    
    # Add new URLs for survey management
    path('api/survey-templates/', views.survey_templates_view, name='survey-templates-api'),
    path('api/survey-templates/<int:template_id>/questions/', views.survey_questions_view, name='survey-questions-api'),
    path('admin/survey-templates/', views.survey_templates_admin_view, name='survey-templates-admin'),
    # Add this to your urlpatterns
    path('api/get-user-survey-questions/', views.get_user_survey_questions, name='get-user-survey-questions'),
    
    # University-specific and hash link survey URLs
    path('survey/link/<uuid:hash_link>/', views.survey_view, name='hashed-survey'),
    
    # Keep your other existing URLs
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('survey/', views.survey_view, name='survey'),
    path('login/', views.login_view, name='login'),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("demo-survey/", views.demo_survey_view, name="demo-survey"),
    path('', views.index_view, name='index'),
]