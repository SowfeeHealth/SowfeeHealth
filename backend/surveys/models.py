from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.core.exceptions import ValidationError

class UserManager(BaseUserManager):
    """
    UserManager allows creation of users in the database
    """
    def create_user(self, email, password=None):
        """
        create_user creates a new user in the database

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
        create_superuser facilitates creation of a super user with admin access

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


class User(AbstractBaseUser, PermissionsMixin):
    """
    User model is used to register and authenticate users
    """
    email = models.EmailField(unique=True)
    is_admin = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
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


def validate_edu_email(value):
    """
    validate_edu_email is a helper function that checks if the email
    address of a user ends with .edu

    value: input email address
    """
    if not value.endswith('.edu'):
        raise ValidationError('Only .edu email addresses are accepted.')


class SurveyResponse(models.Model):
    """
    SurveyResponse model represents a survey response submitted by a student
    """
    id = models.AutoField(primary_key=True)
    student_name = models.CharField(max_length=250)
    school_email = models.EmailField(max_length=250, validators=[validate_edu_email])
    university_id = models.CharField(max_length=250, default="Unknown")
    created = models.DateTimeField(auto_now_add=True)
    q1 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    q2 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    q3 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    q4 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    q5 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])

    class Meta:
        unique_together = ('school_email', 'created')


class FlaggedStudents(models.Model):
    """
    FlaggedStudents model represents a flagged student based on survey responses
    """
    school_email = models.EmailField(max_length=250, validators=[validate_edu_email])
    student_name = models.CharField(max_length=250)
    student_response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE)


class Student(models.Model):
    """
    Student model represents a student registered to take a survey
    """
    school_email = models.EmailField(max_length=250, primary_key=True, validators=[validate_edu_email])
    student_name = models.CharField(max_length=250)
    university_id = models.CharField(max_length=250)


class Institution(models.Model):
    """
    Institution model represents an institution registered with the system
    """
    institution_name = models.CharField(max_length=250)
    institution_email_regex = models.CharField(max_length=250)
    admin_details = models.ForeignKey(User, on_delete=models.CASCADE)