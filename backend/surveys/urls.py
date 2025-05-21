from django.urls import path
from django.contrib.auth.decorators import login_required
from . import views

urlpatterns = [
    path("api/student-responses/", views.student_response_view, name="student-responses-api"),
    path("api/flagged-students/", views.flagged_students_view, name="flagged-students-api"),
    path('api/students/', views.students_view, name='students-api'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('survey/', views.survey_view, name='survey'),
    path('login/', views.login_view, name='login'),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("demo-survey/", views.demo_survey_view, name="demo-survey"),
    path('', views.index_view, name='index'),
]