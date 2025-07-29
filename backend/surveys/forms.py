# forms.py
from django import forms
from .models import SurveyResponse

class SurveyForm(forms.ModelForm):
    class Meta:
        model = SurveyResponse
        fields = ['student_name', 'school_email', 'q1', 'q2', 'q3', 'q4', 'q5']  # Update field names
