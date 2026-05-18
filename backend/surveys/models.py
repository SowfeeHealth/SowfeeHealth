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

    DEFAULT_LIKERT_CHOICES = {
        "1": "Excellent",
        "2": "Good",
        "3": "Neutral",
        "4": "Poor",
        "5": "Very Poor",
    }

    def save(self, *args, **kwargs):
        if self.question_type == QuestionType.TEXT:
            self.category = QuestionCategory.GENERAL
        if self.question_type == QuestionType.LIKERT and self.answer_choices:
            merged = dict(self.DEFAULT_LIKERT_CHOICES)
            merged.update(self.answer_choices)
            self.answer_choices = merged
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
    final_severity = models.CharField(
        max_length=10,
        choices=[
            ('none', 'None'),
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
        ],
        default='none',
        help_text=(
            "Maximum severity across all pipeline stages "
            "(rule engine + per-question assessments)."
        ),
    )
    pipeline_latency_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text=(
            "Total pipeline execution time in ms. "
            "NULL until Celery task completes."
        ),
    )
    inference_mode_used = models.CharField(
        max_length=20,
        choices=[
            ('full', 'Full'),
            ('rule_only', 'Rule Only'),
        ],
        null=True,
        blank=True,
        help_text=(
            "Inference mode actually used when this survey was processed. "
            "Snapshot at submission time. Persists for audit even if "
            "Institution.inference_mode changes later."
        ),
    )
    final_severity_order = models.IntegerField(
        default=0,
        db_index=True,
        help_text=(
            "Integer magnitude of final_severity (0=none, 1=low, 2=medium, "
            "3=high). Auto-synced from final_severity in save() using "
            "SEVERITY_ORDER from moderation/schemas.py. Used for DB-level "
            "ordering since string ordering on enum names is alphabetic."
        ),
    )

    class Meta:
        indexes = [
            models.Index(fields=['flagged', '-final_severity_order', '-created']),
        ]

    def __str__(self):
        name = None
        if self.student:
            name = getattr(self.student, 'name', None)
        elif self.anonymous_student:
            name = getattr(self.anonymous_student, 'name', None)

        if name:
            return f"{name} - {str(self.created)}"
        return f"Survey Response {self.id} - {str(self.created)}"

    def save(self, *args, **kwargs):
        """Auto-sync final_severity_order from final_severity before save.

        Handles update_fields: if caller specifies update_fields containing
        'final_severity', also persist 'final_severity_order' to keep them in sync.
        """
        from .moderation.schemas import SEVERITY_ORDER, Severity
        try:
            self.final_severity_order = SEVERITY_ORDER[Severity(self.final_severity)]
        except (ValueError, KeyError) as exc:
            raise ValueError(
                f"Invalid final_severity={self.final_severity!r} on SurveyResponse "
                f"(id={self.pk}). Must be one of: {[s.value for s in Severity]}"
            ) from exc
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields = set(update_fields)
            if 'final_severity' in update_fields:
                update_fields.add('final_severity_order')
                kwargs['update_fields'] = update_fields
        super().save(*args, **kwargs)


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


class FlaggingRule(models.Model):
    """Institution-configured rule for Stage 1a flagging.

    Lives in tenant schema. Each institution configures its own rules.

    severity_order is auto-synced from severity in save() to enable
    DB-level magnitude ordering. String ordering on severity values
    ('high'/'medium'/'low'/'none') is alphabetic and gives wrong order.
    """

    RULE_TYPES = [
        ('any_question', 'Any Question'),
        ('sum', 'Sum'),
        ('average', 'Average'),
    ]
    COMPARISONS = [('gte', '>='), ('lte', '<=')]
    SEVERITIES = [
        ('none', 'None'),
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    category = models.CharField(max_length=50)
    rule_type = models.CharField(max_length=20, choices=RULE_TYPES)
    threshold = models.FloatField()
    comparison = models.CharField(max_length=3, choices=COMPARISONS)
    severity = models.CharField(max_length=10, choices=SEVERITIES)
    severity_order = models.IntegerField(
        default=0,
        db_index=True,
        help_text=(
            "Integer magnitude of severity (0=none, 1=low, 2=medium, 3=high). "
            "Auto-synced from severity in save() using SEVERITY_ORDER from "
            "moderation/schemas.py. Used for DB-level ordering since string "
            "ordering on enum names is alphabetic, not magnitude."
        ),
    )
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-severity_order', 'category']
        indexes = [
            models.Index(fields=['category', 'enabled']),
            models.Index(fields=['enabled']),
        ]

    def __str__(self):
        return f"{self.category} {self.rule_type} {self.comparison} {self.threshold} → {self.severity}"

    def save(self, *args, **kwargs):
        """Auto-sync severity_order from severity before save."""
        from .moderation.schemas import SEVERITY_ORDER, Severity
        try:
            self.severity_order = SEVERITY_ORDER[Severity(self.severity)]
        except (ValueError, KeyError) as exc:
            raise ValueError(
                f"Invalid severity={self.severity!r} on FlaggingRule "
                f"(id={self.pk}). Must be one of: {[s.value for s in Severity]}"
            ) from exc
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields = set(update_fields)
            if 'severity' in update_fields:
                update_fields.add('severity_order')
                kwargs['update_fields'] = update_fields
        super().save(*args, **kwargs)

    def to_pydantic(self):
        """Convert this Django model to Pydantic FlaggingRule.

        Used by tasks.py when loading rules for ModerationPipeline.
        """
        from .moderation.schemas import FlaggingRule as PydanticRule, Severity
        return PydanticRule(
            category=self.category,
            rule_type=self.rule_type,
            threshold=self.threshold,
            comparison=self.comparison,
            severity=Severity(self.severity),
            description=self.description or None,
        )


class CrisisAssessmentRecord(models.Model):
    """Per-text-question pipeline assessment record.

    SurveyResponse → CrisisAssessmentRecord is 1-to-N.
    One record per text question that had Stage 1c/1b/2 activity
    (i.e. something happened during processing).

    UniqueConstraint(survey_response, question) prevents duplicates.
    """

    SEVERITY_CHOICES = [
        ('none', 'None'),
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    survey_response = models.ForeignKey(
        SurveyResponse,
        on_delete=models.CASCADE,
        related_name='crisis_assessments',
    )
    question = models.ForeignKey(
        SurveyQuestion,
        on_delete=models.CASCADE,
        related_name='+',
    )

    # Severity from QuestionAssessment.severity_max()
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)

    # Stage 2 LLM output (NULL/empty if rule_only mode or no Stage 2 trigger)
    primary_concern = models.CharField(max_length=50, blank=True)
    counselor_brief = models.TextField(blank=True)
    confidence = models.FloatField(null=True, blank=True)
    evidence_phrases = models.JSONField(default=list)

    # Stage 1c keyword filter (audit + degraded-mode safety net)
    keyword_matches = models.JSONField(default=list)

    # Metadata
    provider = models.CharField(
        max_length=50,
        blank=True,
        help_text="LLM provider (e.g. 'anthropic/claude-sonnet-4-6'). Empty if no Stage 2."
    )
    degraded_mode = models.BooleanField(default=False)
    degraded_reason = models.TextField(blank=True)

    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created']
        constraints = [
            models.UniqueConstraint(
                fields=['survey_response', 'question'],
                name='unique_assessment_per_question',
            ),
        ]
        indexes = [
            models.Index(fields=['survey_response']),
            models.Index(fields=['severity', 'created']),
            models.Index(fields=['degraded_mode']),
        ]

    def __str__(self):
        return f"Assessment for SR#{self.survey_response_id} Q#{self.question_id}: {self.severity}"

    @classmethod
    def from_question_assessment(cls, survey_response, q_assessment):
        """Create a CrisisAssessmentRecord from a QuestionAssessment Pydantic output.

        Pydantic → Django direction. Mirror of FlaggingRule.to_pydantic()
        (which is Django → Pydantic).

        Used by Phase 7b tasks.py after pipeline.process_survey() returns.

        Returns the created record, or None if the QuestionAssessment had
        no notable signal (no keyword match, no Stage 2 assessment, no
        degraded mode) — benign questions are not persisted.

        Args:
            survey_response: SurveyResponse Django instance to link to.
            q_assessment: QuestionAssessment Pydantic instance from pipeline output.

        Returns:
            CrisisAssessmentRecord or None.
        """
        has_keyword = (
            q_assessment.keyword_result is not None
            and q_assessment.keyword_result.matched
        )
        has_assessment = q_assessment.assessment is not None
        has_degraded = q_assessment.degraded_mode

        if not (has_keyword or has_assessment or has_degraded):
            return None

        assessment = q_assessment.assessment
        keyword = q_assessment.keyword_result

        return cls.objects.create(
            survey_response=survey_response,
            question_id=q_assessment.question_id,
            severity=q_assessment.severity_max().value,

            primary_concern=assessment.primary_concern if assessment else "",
            counselor_brief=assessment.counselor_brief if assessment else "",
            confidence=assessment.confidence if assessment else None,
            evidence_phrases=assessment.evidence_phrases if assessment else [],

            keyword_matches=keyword.matched_keywords if keyword else [],

            provider=assessment.provider if assessment else "",
            degraded_mode=q_assessment.degraded_mode,
            degraded_reason=q_assessment.degraded_reason or "",
        )
