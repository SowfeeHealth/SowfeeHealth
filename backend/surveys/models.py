from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.exceptions import ValidationError
import uuid
from django.core.validators import validate_email

# Re-export for backward compatibility — all existing imports still work
from accounts.models import User, UserManager
from tenants.models import Institution


# In SurveyTemplate class
class SurveyTemplate(models.Model):
    id = models.AutoField(primary_key=True)
    hash_link = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    used = models.BooleanField(default=False)

    def __str__(self):
        return f"Survey Template {self.id}"

class AnonymousStudent(models.Model):
    email = models.EmailField(primary_key=True)
    name = models.CharField(null=True, max_length=250)
    survey_template = models.ForeignKey(SurveyTemplate, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email

class QuestionType(models.TextChoices):
    LIKERT = 'likert', 'Likert Scale (1-5)'
    TEXT = 'text', 'Text Response'


class QuestionCategory(models.TextChoices):
    GENERAL = 'general', 'General Question'
    SLEEP = 'sleep', 'Sleep Quality'
    STRESS = 'stress', 'Stress Level'
    SUPPORT = 'support', 'Support Perception'


class SurveyQuestion(models.Model):
    """
    SurveyQuestion represents an individual question in a survey
    """
    id = models.AutoField(primary_key=True)
    survey_template = models.ForeignKey(SurveyTemplate, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(
        max_length=20,
        choices=QuestionType.choices,
        default=QuestionType.LIKERT
    )
    category = models.CharField(
        max_length=20,
        choices=QuestionCategory.choices,
        default=QuestionCategory.GENERAL
    )
    order = models.IntegerField(default=0)
    answer_choices = models.JSONField(blank=True, null=True, help_text='Custom answer choices for Likert scale questions')

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.question_text[:30]}..."

    def clean(self):
        super().clean()
        if self.question_type == QuestionType.TEXT and self.category != QuestionCategory.GENERAL:
            raise ValidationError({
                'category': 'Category can only be set for Likert scale questions. Text questions must use General category.'
            })

    def save(self, *args, **kwargs):
        if self.question_type == QuestionType.TEXT:
            self.category = QuestionCategory.GENERAL
        self.full_clean()
        super().save(*args, **kwargs)


class SurveyResponse(models.Model):
    """
    SurveyResponse represents a complete survey submission by a student
    """
    id = models.AutoField(primary_key=True)
    student = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    anonymous_student = models.ForeignKey(AnonymousStudent, on_delete=models.CASCADE, null=True, blank=True)
    # Option 1: Allow null temporarily during migration
    survey_template = models.ForeignKey(SurveyTemplate, on_delete=models.CASCADE, null=True, blank=True)
    # OR Option 2: Provide a default value
    # survey_template = models.ForeignKey(SurveyTemplate, on_delete=models.CASCADE, default=1)
    created = models.DateTimeField(auto_now_add=True)
    flagged = models.BooleanField(default=False)

    def __str__(self):
        name = None
        if self.student:
            name = getattr(self.student, 'name', None)
        elif self.anonymous_student:
            name = getattr(self.anonymous_student, 'name', None)

        if name:
            return f"{name} - {str(self.created)}"
        return f"Survey Response {self.id} - {str(self.created)}"


class QuestionResponse(models.Model):
    """
    QuestionResponse represents an individual response to a specific question
    """
    id = models.AutoField(primary_key=True)
    survey_response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name='question_responses')
    question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE)
    likert_value = models.IntegerField(null=True, blank=True, validators=[MaxValueValidator(5), MinValueValidator(1)])
    text_response = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ('survey_response', 'question')

    def __str__(self):
        if self.question.question_type == QuestionType.LIKERT:
            return f"Likert response: {self.likert_value}"
        return f"Text response: {self.text_response[:30]}..."
