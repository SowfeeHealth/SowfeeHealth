from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import validate_email


class UserManager(BaseUserManager):
    def create_user(self, email, password=None):
        if not email:
            raise ValueError("Users must have an email address")
        user = self.model(email=self.normalize_email(email))
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None):
        user = self.create_user(email=email, password=password)
        user.is_superuser = True
        user.save(using=self._db)
        return user

    def create_student(self, email, password, institution_details, name):
        student = self.model(
            email=email, role=User.Role.STUDENT, name=name,
            institution_details=institution_details,
        )
        student.set_password(password)
        student.save()
        return student

    def create_admin(self, email, password, institution_details):
        admin = self.model(
            email=email, role=User.Role.INSTITUTION_ADMIN,
            institution_details=institution_details,
        )
        admin.set_password(password)
        admin.save()
        return admin


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        STUDENT = 'student', 'Student'
        INSTITUTION_ADMIN = 'institution_admin', 'Institution Admin'
        COUNSELOR = 'counselor', 'Counselor'
        PARENT = 'parent', 'Parent'

    email = models.EmailField(unique=True, validators=[validate_email])
    is_superuser = models.BooleanField(default=False)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    name = models.CharField(null=True, blank=True, max_length=250)
    institution_details = models.ForeignKey(
        'tenants.Institution', null=True, blank=True, on_delete=models.CASCADE,
    )
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email

    def has_perm(self, perm, obj=None):
        if self.is_superuser:
            return True
        return self.role == self.Role.INSTITUTION_ADMIN

    def has_module_perms(self, app_label):
        return True

    def get_username(self):
        return self.email

    def clean(self):
        super().clean()
        edu_roles = [self.Role.STUDENT, self.Role.INSTITUTION_ADMIN]
        if self.role in edu_roles and not self.email.endswith('.edu'):
            raise ValidationError({
                'email': 'Students and institution admins must use a .edu email.'
            })

    @property
    def is_staff(self):
        return self.is_superuser
