from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.core.exceptions import ValidationError

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


class User(AbstractBaseUser, PermissionsMixin):
    """
    User model is used to register and authenticate users
    """
    email = models.EmailField(unique=True)
    is_admin = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_student = models.BooleanField(default=False)
    is_institution_admin = models.BooleanField(default=False)
     # name required only when user is student 
    name = models.CharField(unique=True, null=True, blank=True, max_length=250)
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
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    q1 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    q2 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    q3 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    q4 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    q5 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    flagged = models.BooleanField(default=False)

    class Meta:
        unique_together = ('student', 'created')

    def __str__(self):
        return f"{self.student.name} - {str(self.created)}"