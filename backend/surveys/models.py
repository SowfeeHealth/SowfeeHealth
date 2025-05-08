from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone

# ✅ Add a custom manager
class UserManager(BaseUserManager):
    def create_user(self, email, password=None):
        if not email:
            raise ValueError("Users must have an email address")
        user = self.model(email=self.normalize_email(email))
        user.set_password(password)  # This hashes the password
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None):
        user = self.create_user(email=email, password=password)
        user.is_admin = True
        user.is_superuser = True
        # 不需要设置 is_staff，因为它是一个属性，会根据 is_admin 自动计算
        # 不需要再次调用 set_password，因为 create_user 已经设置了密码
        user.save(using=self._db)
        return user

class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    is_admin = models.BooleanField(default=False)  # For admin privileges
    is_superuser = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)  # To track when the user joined

    USERNAME_FIELD = 'email'  # Email is the unique identifier for user
    REQUIRED_FIELDS = []  # No other required fields

    objects = UserManager()

    def __str__(self):
        return self.email

    def has_perm(self, perm, obj=None):
        return self.is_admin

    def has_module_perms(self, app_label):
        return True
    
    def get_username(self):
        return self.email  # Use email as username

    @property
    def is_staff(self):
        return self.is_admin  # This will be used for admin access in the Django admin panel


class SurveyResponse(models.Model):
    # Add an explicit id field as the primary key
    id = models.AutoField(primary_key=True)
    student_name = models.CharField(max_length=250)
    school_email = models.EmailField(max_length=250)  # No primary_key=True
    university_id = models.CharField(max_length=250, default="Unknown")
    created = models.DateTimeField(auto_now_add=True)
    q1 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    q2 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    q3 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    q4 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])
    q5 = models.IntegerField(validators=[MaxValueValidator(5), MinValueValidator(1)])

    class Meta:
        # Create a unique constraint instead of a composite primary key
        unique_together = ('school_email', 'created')

class FlaggedStudents(models.Model):
    school_email = models.EmailField(max_length=250)
    student_name = models.CharField(max_length=250)
    student_response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE)

class Student(models.Model):
    school_email = models.EmailField(max_length=250, primary_key=True)
    student_name = models.CharField(max_length=250)
    university_id = models.CharField(max_length=250)
