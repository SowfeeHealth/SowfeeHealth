from django.contrib import admin
from .models import SurveyResult

# Define a custom admin class
class SurveyResultAdmin(admin.ModelAdmin):
    list_display = ('qnum', 'rating')  # Columns to display in the list view
    search_fields = ('qnum',)  # Add a search bar for the 'qnum' field
    list_filter = ('rating',)  # Add a filter sidebar for 'rating'

# Register the model and the custom admin class
admin.site.register(SurveyResult, SurveyResultAdmin)