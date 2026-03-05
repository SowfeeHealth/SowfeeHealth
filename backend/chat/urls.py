
from django.urls import path
from . import views

urlpatterns = [
    path('assignments/', views.assignments, name='assignment-list'),
    path('assignments/<int:pk>/', views.assignment_detail, name='assignment-detail'),
]