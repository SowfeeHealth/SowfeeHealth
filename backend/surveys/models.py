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