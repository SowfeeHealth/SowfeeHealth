from django.contrib import admin
from .models import SurveyResult

# Define a custom admin class
class SurveyResultAdmin(admin.ModelAdmin):
    # Update list_display to show the qnum from the related Question model
    list_display = ('question_qnum', 'rating')  # Use the custom method to show qnum
    search_fields = ('question__qnum',)  # Use double underscore to reference qnum in the related Question model
    list_filter = ('rating',)

    def question_qnum(self, obj):
        # Access the qnum from the related Question object
        return obj.question.qnum if obj.question else None
    question_qnum.short_description = 'Question Number'  # Customize the column title

# Register the model and the custom admin class
admin.site.register(SurveyResult, SurveyResultAdmin)
