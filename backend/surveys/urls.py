from django.urls import path
from . import views

urlpatterns = [
    path("student-survey", views.handleStudentResponses),
    path("flagged-students", views.handleFlaggedStudents),
    path('survey', views.survey_view, name='survey'),  # Survey view that maps survey page to send its responses
    path('', views.index_view, name='index'),  # Root URL maps to the index_view
    path('dashboard/<str:university>/', views.dashboard_view, name='dashboard')
]