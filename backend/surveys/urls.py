from django.urls import path
from . import views

urlpatterns = [
    path("student-survey/", views.student_response_view),
    path("flagged-students/", views.flagged_students_view),
    path('survey/', views.survey_view, name='survey'),  # Survey view that maps survey page to send its responses
    path('', views.index_view, name='index'),  # Root URL maps to the index_view
    path('dashboard/<str:university>/', views.dashboard_view, name='dashboard'),
    path('student', views.students_view, name='student'),
    path('login/', views.login_view, name='login'),
    path("register/", views.register_view, name="register"),
]