"""
Onboards a new school in one step: creates the institution, schema, domain,
admin user, email mapping, default survey template, and hash lookup.

Usage:
    python manage.py onboard_school --name="Northeastern University" \
        --schema=northeastern_university --domain=northeastern.localhost \
        --regex=".+@northeastern\\.edu" --admin-email=admin@northeastern.edu

Password is prompted interactively (never passed as a CLI argument).
"""

import getpass
import re

from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import connection
from django_tenants.utils import schema_context

from tenants.models import Institution, Domain, EmailTenantMapping, SurveyHashLookup
from accounts.models import User
from surveys.models import SurveyTemplate


SCHEMA_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')
MIN_PASSWORD_LENGTH = 8


class Command(BaseCommand):
    help = 'Onboards a new school: institution, admin user, survey template, and all mappings'

    def add_arguments(self, parser):
        parser.add_argument('--name', required=True, help='Institution name')
        parser.add_argument('--schema', required=True, help='Schema name (lowercase letters, numbers, underscores)')
        parser.add_argument('--domain', default='localhost', help='Domain for the tenant (default: localhost)')
        parser.add_argument('--regex', default=r'.+@.*\.edu', help='Email regex pattern for the institution')
        parser.add_argument('--admin-email', required=True, help='Admin user email address')

    def handle(self, *args, **options):
        schema_name = options['schema']
        institution_name = options['name']
        domain_name = options['domain']
        regex_pattern = options['regex']
        admin_email = options['admin_email']

        self._validate(schema_name, admin_email, regex_pattern)
        password = self._prompt_password()

        try:
            tenant = self._create_institution(institution_name, schema_name, domain_name, regex_pattern)
            self._seed_tenant(tenant, admin_email, password)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'\nOnboarding failed: {e}'))
            self._rollback(schema_name)
            raise CommandError('Onboarding aborted. Partial data cleaned up.')

        self._print_summary(institution_name, schema_name, domain_name, admin_email)

    def _validate(self, schema_name, admin_email, regex_pattern):
        if not SCHEMA_PATTERN.match(schema_name):
            raise CommandError(
                f'Invalid schema name "{schema_name}". '
                'Use only lowercase letters, numbers, and underscores. Must start with a letter.'
            )

        if Institution.objects.filter(schema_name=schema_name).exists():
            raise CommandError(f'Schema "{schema_name}" already exists.')

        try:
            validate_email(admin_email)
        except ValidationError:
            raise CommandError(f'Invalid email address: {admin_email}')

        if EmailTenantMapping.objects.filter(email=admin_email).exists():
            raise CommandError(f'Email "{admin_email}" is already mapped to a tenant.')

        try:
            re.compile(regex_pattern)
        except re.error as e:
            raise CommandError(f'Invalid regex pattern: {e}')

    def _prompt_password(self):
        password = getpass.getpass('Admin password: ')
        if len(password) < MIN_PASSWORD_LENGTH:
            raise CommandError(f'Password must be at least {MIN_PASSWORD_LENGTH} characters.')
        confirm = getpass.getpass('Confirm password: ')
        if password != confirm:
            raise CommandError('Passwords do not match.')
        return password

    def _create_institution(self, name, schema, domain, regex):
        self.stdout.write(f'  Creating institution "{name}" (schema: {schema})...')
        tenant = Institution(
            schema_name=schema,
            institution_name=name,
            institution_regex_pattern=regex,
        )
        tenant.save()
        Domain.objects.create(domain=domain, tenant=tenant, is_primary=True)
        self.stdout.write(self.style.SUCCESS('  Done'))
        return tenant

    def _seed_tenant(self, tenant, admin_email, password):
        with schema_context(tenant.schema_name):
            self.stdout.write(f'  Creating admin user ({admin_email})...')
            User.objects.create_admin(
                email=admin_email,
                password=password,
                institution_details=tenant,
            )
            self.stdout.write(self.style.SUCCESS('  Done'))

            self.stdout.write('  Creating default survey template...')
            template = SurveyTemplate.objects.create(used=False)
            self.stdout.write(self.style.SUCCESS('  Done'))

        EmailTenantMapping.objects.create(email=admin_email, schema_name=tenant.schema_name)
        SurveyHashLookup.objects.create(hash_link=template.hash_link, tenant=tenant)
        self.stdout.write(self.style.SUCCESS('  Email mapping and hash lookup created'))

    def _rollback(self, schema_name):
        self.stderr.write('  Cleaning up partial data...')
        connection.set_schema_to_public()
        EmailTenantMapping.objects.filter(schema_name=schema_name).delete()
        SurveyHashLookup.objects.filter(tenant__schema_name=schema_name).delete()
        try:
            tenant = Institution.objects.get(schema_name=schema_name)
            tenant.delete(force_drop=True)
        except Institution.DoesNotExist:
            pass

    def _print_summary(self, name, schema, domain, email):
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Onboarding complete!'))
        self.stdout.write(f'  Institution:  {name}')
        self.stdout.write(f'  Schema:       {schema}')
        self.stdout.write(f'  Domain:       {domain}')
        self.stdout.write(f'  Admin:        {email}')
        self.stdout.write(f'  Survey:       1 default template (inactive)')
