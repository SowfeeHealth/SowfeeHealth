
from django.urls import path
from . import views

urlpatterns = [
    path('assignments/', views.assignments, name='assignment-list'),
    path('assignments/<int:pk>/', views.assignment_detail, name='assignment-detail'),
    path('messages/<int:userId>/', views.chat_messages, name='chat-messages'),
    path('counselors/', views.counselors, name='counselors'),
    path('users/<int:pk>/promote/', views.promote_to_counselor, name='promote-to-counselor'),
]