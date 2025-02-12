from django.contrib import admin
from .models import SurveyResult

# Define a custom admin class
class SurveyResultAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'email', 'question1_qnum', 'question1_rating',
        'question2_qnum', 'question2_rating', 'question3_qnum', 'question3_rating',
        'question4_qnum', 'question4_rating', 'question5_qnum', 'question5_rating'
    )  # Display question number and ratings
    search_fields = ('name', 'email')  # Searching by name and email instead of question qnums
    list_filter = ('q1', 'q2', 'q3', 'q4', 'q5')  # Filter by individual questions (updated field names)

    def question1_qnum(self, obj):
        return 1  # Question number 1
    question1_qnum.short_description = 'Q1'

    def question1_rating(self, obj):
        return obj.q1  # Display the rating for question 1
   
