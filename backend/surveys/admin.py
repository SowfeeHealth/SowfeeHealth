from django.contrib import admin
from .models import SurveyResponse, User, Institution, SurveyTemplate, SurveyQuestion, QuestionResponse
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

# Configure admin interface for SurveyQuestion model
class SurveyQuestionInline(admin.TabularInline):
    model = SurveyQuestion
    extra = 1

# Configure admin interface for SurveyTemplate model
class SurveyTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'institution')  # removed 'created'
    list_filter = ('institution',)
    inlines = [SurveyQuestionInline]

# Configure admin interface for QuestionResponse model
class QuestionResponseInline(admin.TabularInline):
    model = QuestionResponse
    extra = 0

# Configure admin interface for SurveyResponse model
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ('student', 'survey_template', 'created', 'flagged')
    list_filter = ('created', 'flagged', 'survey_template')
    search_fields = ('student__name', 'student__email')
    ordering = ('-created',)
    inlines = [QuestionResponseInline]

# Configure admin interface for User model
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'name', 'is_admin', 'is_superuser', 'date_joined', 'institution_details')
    fieldsets = (
        (None, {"fields": ("email", "name", "password", "institution_details")}),
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

# Configure admin interface for SurveyQuestion model
class SurveyQuestionAdmin(admin.ModelAdmin):
    list_display = ('question_text', 'question_type', 'category', 'order')
    list_filter = ('question_type', 'category')
    
    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "category":
            if request.resolver_match.kwargs.get('object_id'):
                obj = self.get_object(request, request.resolver_match.kwargs['object_id'])
                if obj and obj.question_type == 'text':
                    kwargs['choices'] = [('general', 'General Question')]
        return super().formfield_for_choice_field(db_field, request, **kwargs)
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj and obj.question_type == 'text':
            form.base_fields['category'].disabled = True
        return form

# Keep all existing registrations
admin.site.register(SurveyResponse, SurveyResponseAdmin)
admin.site.register(User, UserAdmin)
admin.site.register(Institution, InstitutionAdmin)
admin.site.register(SurveyTemplate, SurveyTemplateAdmin)
# Replace the simple SurveyQuestion registration with our custom admin
admin.site.register(SurveyQuestion, SurveyQuestionAdmin)
admin.site.register(QuestionResponse)