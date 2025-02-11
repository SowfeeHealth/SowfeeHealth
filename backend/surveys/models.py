from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator

class SurveyResponse(models.Model):
    student_name = models.CharField(max_length=250)
    school_email = models.EmailField(max_length=250)
    created = models.DateTimeField(auto_now_add=True)
    q1 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    q2 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    q3 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    q4 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    q5 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])

class FlaggedStudents(models.Model):
    school_email = models.EmailField(max_length=250)
    student_name = models.CharField(max_length=250)
    student_response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE)