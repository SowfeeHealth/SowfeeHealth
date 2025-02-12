# forms.py
from django import forms
from .models import SurveyResult

class SurveyForm(forms.ModelForm):
    class Meta:
        model = SurveyResult
        fields = ['name', 'email', 'question', 'rating']  # Update field names
