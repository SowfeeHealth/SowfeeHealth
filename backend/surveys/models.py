from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.core.exceptions import ValidationError
import uuid
from django.core.validators import validate_email

class Institution(models.Model):
    """
    Institution model represents an institution registered with the system
    """
    institution_name = models.CharField(max_length=250)
    institution_regex_pattern = models.CharField(max_length=250)

    def __str__(self):
        return self.institution_name


class UserManager(BaseUserManager):
    """
    UserManager allows creation of users in the database. NOTE: application-
    wise, there are two users: students and institution admins. Internally,
    there is a superuser, admin, and staff.
    """
    def create_user(self, email, password=None):
        """
        create_user creates a new user in the database (use only for development)

        email: email address of the user
        password: password chosen by the user
        """
        if not email:
            raise ValueError("Users must have an email address")
        
        user = self.model(email=self.normalize_email(email))
        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password=None):
        """
        create_superuser facilitates creation of a super user with admin access (use only for development)

        email: email address of the user
        password: password chosen by the user
        """
        user = self.create_user(email=email, password=password)
        
        # Give all the permissions to the user
        user.is_admin = True
        user.is_superuser = True

        # Save permission changes to the database
        user.save(using=self._db)

        return user

    def create_student(self, email, password, institution_details, name):
        """
        create_student creates a student in the database. NOTE: validation
        of email, passwork, and institution_details will be done by the view
        that calls this function.

        email: email corresponding to the student
        password: password corresponding to the student
        institution_details: institution corresponding to the student
        """
        student = self.model(email=email, is_student=True, name=name, institution_details=institution_details)
        student.set_password(password)
        student.save()

        return student

    def create_admin(self, email, password, institution_details):
        """
        create_admin creates a new admin in the database. NOTE: validation
        of email, passwork, and institution_details will be done by the view
        that calls this function.

        email: email corresponding to the admin
        password: password corresponding to the admin
        institution_details: institution corresponding to the admin
        """
        admin = self.model(email=email, is_institution_admin=True, institution_details=institution_details)
        admin.set_password(password)
        admin.save()

        return admin



def validate_edu_email(value):
    """
    validate_edu_email is a helper function that checks if the email
    address of a user ends with .edu

    value: input email address
    """
    if not value.endswith('.edu'):
        raise ValidationError('Only .edu email addresses are accepted.')
        
class User(AbstractBaseUser, PermissionsMixin):
    """
    User model is used to register and authenticate users
    """
    email = models.EmailField(unique=True, validators=[validate_email, validate_edu_email])
    is_admin = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_student = models.BooleanField(default=False)
    is_institution_admin = models.BooleanField(default=False)
     # name required only when user is student 
    name = models.CharField(null=True, blank=True, max_length=250)
    # institution_details required only when user is student or admin                            
    institution_details = models.ForeignKey(Institution, null=True, blank=True, on_delete=models.CASCADE)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email

    def has_perm(self, perm, obj=None):
        return self.is_admin

    def has_module_perms(self, app_label):
        return True
    
    def get_username(self):
        return self.email

    @property
    def is_staff(self):
        return self.is_admin


# In SurveyTemplate class
class SurveyTemplate(models.Model):
    """
    SurveyTemplate represents a survey configuration for a specific institution
    """
    id = models.AutoField(primary_key=True)
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE)
    hash_link = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    used = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Survey for {self.institution.institution_name}"


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
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    # Option 1: Allow null temporarily during migration
    survey_template = models.ForeignKey(SurveyTemplate, on_delete=models.CASCADE, null=True)
    # OR Option 2: Provide a default value
    # survey_template = models.ForeignKey(SurveyTemplate, on_delete=models.CASCADE, default=1)
    created = models.DateTimeField(auto_now_add=True)
    flagged = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.student.name} - {str(self.created)}"


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