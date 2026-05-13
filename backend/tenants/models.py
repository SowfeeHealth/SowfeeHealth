from django.db import models
from django_tenants.models import TenantMixin, DomainMixin
import uuid


class Institution(TenantMixin):
    institution_name = models.CharField(max_length=250)
    institution_regex_pattern = models.CharField(max_length=250)
    auto_create_schema = True

    def __str__(self):
        return self.institution_name


class Domain(DomainMixin):
    pass


class SurveyHashLookup(models.Model):
    hash_link = models.UUIDField(unique=True)
    tenant = models.ForeignKey(
        Institution, on_delete=models.CASCADE, related_name='hash_lookups',
    )

    def __str__(self):
        return str(self.hash_link)


class EmailTenantMapping(models.Model):
    """
    Public-schema lookup table: maps a user's email to their tenant schema.
    Used during login and middleware to resolve the correct tenant before
    Django's AuthenticationMiddleware loads the User.
    """
    email = models.EmailField(unique=True)
    schema_name = models.CharField(max_length=63)

    def __str__(self):
        return f"{self.email} → {self.schema_name}"
