from django.urls import path
from . import views

urlpatterns = [
    path("student-survey", views.handleStudentResponses),
    path("flagged-students", views.handleFlaggedStudents),
]