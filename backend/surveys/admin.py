from django.contrib import admin
from .models import SurveyResponse, User, Institution

# Description of ModelAdmin attributes:
# list_dispay: which fields are represented in the list display interface in admin
# list_filter: activate filters in the right side bar of the admin interface
# search_fields: fields used in searching for database records
# ordering: field used to order the database records
# fieldsets: fields displayed in the change interface of the admin page
# add_fieldsets: fields displayed when adding a new user from the admin page

# Configure admin interface for SurveyResponse model
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ('student__name', 'student__email', 'created', 'q1', 'q2', 'q3', 'q4', 'q5')
    list_filter = ('created', 'q1', 'q2', 'q3', 'q4', 'q5', 'flagged')
    search_fields = ('student__name', 'student__email')
    ordering = ('-created',)


# Configure admin interface for User model
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'name', 'is_admin', 'is_superuser', 'date_joined', 'institution_details')
    fieldsets = (
        ("Personal Information", {"fields": ("email", "name", "password", "institution_details")}),
        ('Permissions', {"fields": ("is_institution_admin", "is_superuser", "groups", "user_permissions")}),
        ('Important dates', {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"fields": ("email", "name", "password1", "password2", "is_institution_admin", "institution_details")}),
    )
    search_fields = ('email', "name")
    list_filter = ('is_admin', 'is_institution_admin', "date_joined")
    ordering = ('email',)


# Configure admin interface for Institution model
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ('institution_name', 'institution_regex_pattern')
    search_fields = ('institution_name',)


# Register models to the admin interface
admin.site.register(SurveyResponse, SurveyResponseAdmin)

admin.site.register(User, UserAdmin)

admin.site.register(Institution, InstitutionAdmin)