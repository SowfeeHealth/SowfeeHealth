from django.contrib import admin
from .models import SurveyResponse, FlaggedStudents, User, Student

# list_dispay: which fields are represented in the change interface of the model in admin
# list_filter: activate filters in the right side bar of the admin interface
# search_fields: fields used in searching for database records
# ordering: field used to order the database records

# Configure admin interface for SurveyResponse model
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ('student_name', 'school_email', 'created', 'q1', 'q2', 'q3', 'q4', 'q5')
    list_filter = ('created', 'q1', 'q2', 'q3', 'q4', 'q5')
    search_fields = ('student_name', 'school_email')
    ordering = ('-created',)

# Configure admin interface for FlaggedStudents model
class FlaggedStudentsAdmin(admin.ModelAdmin):
    list_display = ('student_name', 'school_email', 'student_response')
    search_fields = ('student_name', 'school_email')
    list_filter = ('student_response',)

# Configure admin interface for User model
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'is_admin', 'date_joined')
    search_fields = ('email',)
    list_filter = ('is_admin',)

# Configure admin interface for Student model
class StudentAdmin(admin.ModelAdmin):
    list_display = ('student_name', 'school_email', 'university_id')
    search_fields = ('student_name', 'school_email')
    list_filter = ('university_id',)

# Register models to the admin interface
admin.site.register(SurveyResponse, SurveyResponseAdmin)

admin.site.register(FlaggedStudents, FlaggedStudentsAdmin)

admin.site.register(User, UserAdmin)

admin.site.register(Student, StudentAdmin)