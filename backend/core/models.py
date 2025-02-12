from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

# Define the SurveyResult model to store the answers for each question
class SurveyResult(models.Model):
    # ForeignKey to relate SurveyResult to a Question (one-to-many relationship)
    name = models.CharField(max_length=255)
    email = models.EmailField()
    q1 = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], default=1)
    q2 = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], default=1)
    q3 = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], default=1)
    q4 =  models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], default=1)
    q5 =  models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], default=1)
    flagged = models.BooleanField(default=False)  # Flag students for critical responses
    submitted_at = models.DateTimeField(auto_now=True)  # Track latest submission time

    class Meta:
        unique_together = ('name', 'email')  # Ensure (name, email) is unique

    def save(self, *args, **kwargs):
        # Automatically set flagged status based on q2 response (adjust the logic if needed)
        self.flagged = int(self.q2) >= 3  # Set flagged to True if q2 is less than 3
        super().save(*args, **kwargs)  # Call the original save method

    def __str__(self):
        return (f"Survey Result for {self.name} ({self.email}): "
                f"Q1: {self.q1}, Q2: {self.q2}, "
                f"Q3: {self.q3}, Q4: {self.q4}, "
                f"Q5: {self.q5}")


