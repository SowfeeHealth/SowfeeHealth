from django.contrib import admin
from .models import SurveyResponse, FlaggedStudents, Student

class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ('student_name', 'school_email', 'created', 'q1', 'q2', 'q3', 'q4', 'q5')
    list_filter = ('created', 'q1', 'q2', 'q3', 'q4', 'q5')
    search_fields = ('student_name', 'school_email')
    ordering = ('-created',)  # Orders by most recent first

class FlaggedStudentsAdmin(admin.ModelAdmin):
    list_display = ('student_name', 'school_email', 'student_response')  # Display these fields in the admin list view
    search_fields = ('student_name', 'school_email')  # Enable search by student name and email
    list_filter = ('student_response',)  # Add a filter option by student response

admin.site.register(SurveyResponse, SurveyResponseAdmin)

admin.site.register(FlaggedStudents, FlaggedStudentsAdmin)

admin.site.register(Student)