# forms.py
from django import forms
from .models import SurveyResult

class SurveyForm(forms.ModelForm):
    class Meta:
        model = SurveyResult
        fields = ['name', 'email', 'q1', 'q2', 'q3', 'q4', 'q5']  # Update field names
