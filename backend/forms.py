# forms.py
from django import forms
from .models import SurveyResponse

class SurveyForm(forms.ModelForm):
    class Meta:
        model = SurveyResponse
        fields = ['name', 'email', 'question_1', 'question_2', 'question_3', 'question_4', 'question_5']
