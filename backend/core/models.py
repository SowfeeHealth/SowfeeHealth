from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

# Define a Question model to store each individual question
class Question(models.Model):
    qnum = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.CharField(max_length=255)  # Assuming you'd have some text for each question

    def __str__(self):
        return f"Question {self.qnum}"

# Define the SurveyResult model to store the answers for each question
class SurveyResult(models.Model):
    # ForeignKey to relate SurveyResult to a Question (one-to-many relationship)
    name = models.CharField(max_length=255)
    email = models.CharField(max_length=255)
    question = models.ForeignKey(Question, on_delete=models.CASCADE) 
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])

    def __str__(self):
        return f"Result for Question {self.question.qnum}: Rating {self.rating}"


